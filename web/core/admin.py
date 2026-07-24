import csv

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet
from django.http import HttpResponse

from .models import Choice, JoinerProgress, Material, Question, Quiz


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


@admin.register(JoinerProgress)
class JoinerProgressAdmin(admin.ModelAdmin):
    # Read-mostly: progress is written by the joiner flow, not hand-edited. (P13 CSV export lands here in Phase 4.)
    list_display = ("user", "material", "status", "score", "passed", "completed_at")
    list_filter = ("status", "passed", "material")
    search_fields = ("user__username", "user__email", "material__title")
    readonly_fields = ("user", "material", "status", "score", "passed", "submitted_at", "completed_at")
    actions = ["export_as_csv"]

    def has_add_permission(self, request):
        return False

    @admin.action(description="Export selected as CSV")
    def export_as_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="joiner_progress.csv"'
        writer = csv.writer(response)
        writer.writerow(["joiner name", "email", "material title", "status", "score", "passed", "completed_at"])
        for p in queryset.select_related("user", "material"):
            writer.writerow([_csv_safe(v) for v in (
                p.user.get_full_name() or p.user.get_username(),
                p.user.email,
                p.material.title,
                p.status,
                "" if p.score is None else p.score,
                "" if p.passed is None else p.passed,
                p.completed_at.isoformat() if p.completed_at else "",
            )])
        return response
