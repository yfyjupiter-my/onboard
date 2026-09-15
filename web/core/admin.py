import csv
import logging

from django.contrib import admin, messages
from django.contrib.admin.options import IncorrectLookupParameters
from django.contrib.admin.utils import display_for_value
from django.contrib.admin.widgets import AdminFileWidget
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, transaction
from django.db.models import Count, F, Max, Q, Value
from django.db.models.functions import Greatest
from django.forms.models import BaseInlineFormSet
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import path
from django.utils.html import format_html, format_html_join

logger = logging.getLogger(__name__)

from .models import Choice, Joiner, JoinerProgress, Material, Question, Quiz

# BUS-013: "View site" pointed at the joiner frontend, which rejects staff (T6.6 split sessions).
admin.site.site_url = None


def _csv_safe(value):
    # Neutralize spreadsheet formula injection: cells starting with = + - @ (or a
    # leading control char) are executed as formulas by Excel/Sheets. Prefix a quote.
    s = "" if value is None else str(value)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s


class ReplaceableFileInput(AdminFileWidget):
    # "Clear" checkbox swapped for a Remove button (MaterialAdmin.remove_file_view); a new upload is a replace.
    template_name = "admin/widgets/removable_file_input.html"


class QuizInline(admin.StackedInline):
    model = Quiz
    extra = 0


class ChoiceInlineFormSet(BaseInlineFormSet):
    # BUS-001: a question must have exactly one correct choice, else it's unscoreable/unpassable.
    def clean(self):
        super().clean()
        total = correct = 0
        for form in self.forms:
            cd = getattr(form, "cleaned_data", None)
            if not cd or cd.get("DELETE") or not cd.get("text"):
                continue  # skip empty extra rows and deletions
            total += 1
            if cd.get("is_correct"):
                correct += 1
        if total and correct != 1:
            raise ValidationError("Each question needs exactly one correct choice.")


class ChoiceInline(admin.TabularInline):
    model = Choice
    formset = ChoiceInlineFormSet
    extra = 2


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 1


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ("title", "chapter", "type", "is_active", "locked", "created_at")
    list_filter = ("chapter", "type", "is_active", "locked")
    search_fields = ("title",)
    exclude = ("description",)  # user request: hide "Image description" row; alt falls back to title
    inlines = [QuizInline]
    formfield_overrides = {models.FileField: {"widget": ReplaceableFileInput}}

    def save_model(self, request, obj, form, change):
        old = form.initial.get("file") if change else None  # clean() may also drop a stale file, so compare names, not changed_data
        super().save_model(request, obj, form, change)
        if old and old.name != obj.file.name:
            # Replaced or cleared: drop the orphaned MinIO object, only once the row is committed.
            storage, name = old.storage, old.name
            transaction.on_commit(lambda: storage.delete(name))

    def get_urls(self):
        return [
            path(
                "<int:pk>/remove-file/",
                self.admin_site.admin_view(self.remove_file_view),
                name="core_material_remove_file",
            ),
        ] + super().get_urls()

    def remove_file_view(self, request, pk):
        # POST only (the widget button submits the change form, so its CSRF token rides along).
        if request.method != "POST":
            return redirect("admin:core_material_change", pk)
        obj = get_object_or_404(self.get_queryset(request), pk=pk)
        if not self.has_change_permission(request, obj):
            raise PermissionDenied
        if obj.file and not obj.url:
            # Nothing left to show: PDF/video/image render from the file, removing it would break the joiner page.
            self.message_user(
                request,
                "Can't remove the only content. Add a URL and save, or upload a replacement file.",
                messages.ERROR,
            )
        elif obj.file:
            # File + URL conflict: drop the file and let the URL take over (T6.14: a video stays a video).
            storage, name = obj.file.storage, obj.file.name
            with transaction.atomic():
                obj.file = ""
                if obj.type != Material.VIDEO:
                    obj.type = Material.LINK
                obj.save(update_fields=["file", "type"])
                transaction.on_commit(lambda: storage.delete(name))
            self.message_user(request, f"File removed. This material now shows its URL (type: {obj.get_type_display()}).", messages.SUCCESS)
        return redirect("admin:core_material_change", pk)


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ("material", "pass_mark")
    inlines = [QuestionInline]


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("text", "quiz", "order")
    list_filter = ("quiz",)
    inlines = [ChoiceInline]


# ponytail: admin index lists models alphabetically (Questions before Quizzes).
# Sort core's models by this order instead; unlisted models keep falling to the end.
_MODEL_ORDER = {"Material": 0, "Quiz": 1, "Question": 2, "Joiner": 3}
_default_get_app_list = admin.site.get_app_list


def _get_app_list(request, app_label=None):
    app_list = _default_get_app_list(request, app_label)
    for app in app_list:
        if app["app_label"] == "core":
            app["models"].sort(key=lambda m: _MODEL_ORDER.get(m["object_name"], 99))
    return app_list


admin.site.get_app_list = _get_app_list


@admin.register(Joiner)
class JoinerAdmin(admin.ModelAdmin):
    # One row per joiner; click through for their per-material progress. (P13 CSV export.)
    list_display = ("name", "email", "completed", "last_activity", "is_active")
    list_filter = ("is_active",)
    search_fields = ("username", "first_name", "last_name", "email")
    readonly_fields = ("username", "first_name", "last_name", "email", "is_active", "date_joined", "incomplete_materials", "progress_table")
    actions = ["export_as_csv"]

    def has_add_permission(self, request):
        return False  # joiner accounts are created/deleted in the Users admin

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        total = Material.objects.filter(is_active=True).count()
        return (
            super().get_queryset(request).filter(is_staff=False).annotate(
                completed_count=Count("progress", filter=Q(progress__status=JoinerProgress.COMPLETED,
                                                            progress__material__is_active=True)),
                total_count=Value(total),
                # Postgres GREATEST skips NULLs: last login or last completion, whichever is later.
                last_activity=Greatest(F("last_login"), Max("progress__completed_at")),
            )
        )

    @admin.display(description="joiner", ordering="username")
    def name(self, obj):
        return obj.get_full_name() or obj.get_username()

    def _active_progress(self, obj):
        # Every active material in checklist order, paired with this joiner's progress row (None = never opened).
        # Read-only: progress is written by the joiner flow, never hand-edited.
        rows = {p.material_id: p for p in obj.progress.all()}
        return [(m, rows.get(m.id)) for m in Material.objects.filter(is_active=True).order_by("chapter", "created_at")]

    @admin.display(description="incomplete materials")
    def incomplete_materials(self, obj):
        pending = [(m, p) for m, p in self._active_progress(obj) if not p or p.status != JoinerProgress.COMPLETED]
        if not pending:
            return "None, all active materials completed."
        return format_html("<ul style=\"margin:0;padding-left:1.2em\">{}</ul>", format_html_join(
            "", "<li>{} ({})</li>",
            ((m.title, p.get_status_display() if p else "Not started") for m, p in pending),
        ))

    # T6.16: replaces the progress inline, which only had rows for materials the joiner had opened.
    @admin.display(description="progress")
    def progress_table(self, obj):
        head = format_html_join("", "<th>{}</th>", ((h,) for h in (
            "Material", "Status", "Score", "Passed", "Submitted at", "Completed at")))
        body = format_html_join("", "<tr>{}</tr>", ((format_html_join("", "<td>{}</td>", ((v,) for v in (
            m.title,
            p.get_status_display() if p else "Not started",
            display_for_value(p and p.score, "-"),
            display_for_value(p and p.passed, "-", boolean=p is not None and p.passed is not None),
            display_for_value(p and p.submitted_at, "-"),
            display_for_value(p and p.completed_at, "-"),
        ))),) for m, p in self._active_progress(obj)))
        return format_html("<table><thead><tr>{}</tr></thead><tbody>{}</tbody></table>", head, body)

    @admin.display(description="completed", ordering="completed_count")
    def completed(self, obj):
        return f"{obj.completed_count} / {obj.total_count}"

    # BUS-015/016: login or completion time, not live presence; never-active joiners sort last when newest-first (admin reverses this).
    @admin.display(description="last login / completion", ordering=F("last_activity").asc(nulls_first=True))
    def last_activity(self, obj):
        return obj.last_activity

    def get_urls(self):
        # "Export CSV" buttons: changelist toolbar (everything matching the current
        # filters/search, no row selection needed) and one joiner's own page.
        return [
            path(
                "export-csv/",
                self.admin_site.admin_view(self.export_all_view),
                name="core_joiner_export",
            ),
            path(
                "<int:pk>/export-csv/",
                self.admin_site.admin_view(self.export_one_view),
                name="core_joiner_export_one",
            ),
        ] + super().get_urls()

    def export_all_view(self, request):
        self._require_export_perm(request)
        try:
            changelist = self.get_changelist_instance(request)
        except IncorrectLookupParameters:
            # SEC-013: a bad filter value is a 500 here; the stock changelist_view
            # catches this and bounces to an unfiltered list. Do the same.
            return redirect("admin:core_joiner_changelist")
        return self._csv(request, changelist.get_queryset(request))

    def export_one_view(self, request, pk):
        # SEC-012: both permissions before the lookup, else 403-vs-404 says whether the pk exists.
        self._require_export_perm(request)
        joiner = get_object_or_404(self.get_queryset(request), pk=pk)
        return self._csv(request, [joiner])

    @admin.action(description="Export selected as CSV")
    def export_as_csv(self, request, queryset):
        return self._csv(request, queryset)

    def _require_export_perm(self, request):
        # SEC-012: the rows are JoinerProgress, so view_joiner alone isn't enough.
        if not self.has_view_permission(request) or not request.user.has_perm("core.view_joinerprogress"):
            raise PermissionDenied

    def _csv(self, request, joiners):
        self._require_export_perm(request)  # choke point: all three export paths land here
        queryset = JoinerProgress.objects.filter(user__in=joiners)
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="joiner_progress.csv"'
        writer = csv.writer(response)
        writer.writerow(["joiner name", "email", "material title", "status", "score", "passed", "completed_at"])
        rows = 0
        for p in queryset.select_related("user", "material"):
            rows += 1
            writer.writerow([_csv_safe(v) for v in (
                p.user.get_full_name() or p.user.get_username(),
                p.user.email,
                p.material.title,
                p.status,
                "" if p.score is None else p.score,
                "" if p.passed is None else p.passed,
                p.completed_at.isoformat() if p.completed_at else "",
            )])
        # COM-004: a whole-table PII export is one click and leaves no admin history.
        logger.info("joiner CSV export by %s: %d rows", request.user.get_username(), rows)
        return response
