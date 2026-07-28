import csv
import logging

from django.contrib import admin
from django.contrib.admin.options import IncorrectLookupParameters
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Max, Q, Value
from django.forms.models import BaseInlineFormSet
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import path

logger = logging.getLogger(__name__)

from .models import Choice, Joiner, JoinerProgress, Material, Question, Quiz


def _csv_safe(value):
    # Neutralize spreadsheet formula injection: cells starting with = + - @ (or a
    # leading control char) are executed as formulas by Excel/Sheets. Prefix a quote.
    s = "" if value is None else str(value)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s


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
    list_display = ("title", "type", "is_active", "created_at")
    list_filter = ("type", "is_active")
    search_fields = ("title",)
    inlines = [QuizInline]


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


class ProgressInline(admin.TabularInline):
    # Read-only: progress is written by the joiner flow, never hand-edited.
    model = JoinerProgress
    fields = ("material", "status", "score", "passed", "submitted_at", "completed_at")
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Joiner)
class JoinerAdmin(admin.ModelAdmin):
    # One row per joiner; click through for their per-material progress. (P13 CSV export.)
    list_display = ("name", "email", "completed", "last_activity", "is_active")
    list_filter = ("is_active",)
    search_fields = ("username", "first_name", "last_name", "email")
    readonly_fields = ("username", "first_name", "last_name", "email", "is_active", "date_joined")
    inlines = [ProgressInline]
    actions = ["export_as_csv"]

    def has_add_permission(self, request):
        return False  # joiner accounts are created/deleted in the Users admin

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        total = Material.objects.filter(is_active=True).count()
        return (
            super().get_queryset(request).filter(is_staff=False).annotate(
                completed_count=Count("progress", filter=Q(progress__status=JoinerProgress.COMPLETED)),
                total_count=Value(total),
                last_activity=Max("progress__completed_at"),
            )
        )

    @admin.display(description="joiner", ordering="username")
    def name(self, obj):
        return obj.get_full_name() or obj.get_username()

    @admin.display(description="completed", ordering="completed_count")
    def completed(self, obj):
        return f"{obj.completed_count} / {obj.total_count}"

    @admin.display(description="last activity", ordering="last_activity")
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
