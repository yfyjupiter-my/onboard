from itertools import groupby
from operator import attrgetter

from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import JoinerProgress, Material


class JoinerLoginForm(AuthenticationForm):
    """Frontend login is joiners-only; staff (HR/IT) use /admin/login/."""

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if user.is_staff:
            raise ValidationError(
                "Staff accounts sign in through the admin site.", code="staff_forbidden"
            )


def _open_material(request, pk):
    # T6.5: server-side gate for every material endpoint, so a locked material can't be
    # reached by typing its URL. BUS-010: returns None when locked; callers redirect home
    # (the checklist explains the lock) instead of a bare 403 page.
    material = get_object_or_404(Material, pk=pk, is_active=True)
    if not (material.file or (material.embeds_url and material.url)):
        return None  # ROB-005: file-less PDF/video/image (admin blocks it; shell/imports don't) -> home, not 500
    return None if material.is_locked_for(request.user) else material


@login_required
def checklist(request):
    # All active materials left-joined to this user's progress. No lazy create here
    # (progress rows are created on first material view, per P3/P5).
    progress = {p.material_id: p for p in request.user.progress.all()}
    quiz_material_ids = set(
        Material.objects.filter(is_active=True, quiz__isnull=False).values_list("id", flat=True)
    )
    materials = list(Material.objects.filter(is_active=True).order_by("chapter", "created_at"))
    completed = {mid for mid, p in progress.items() if p.status == JoinerProgress.COMPLETED}
    locked = Material.locked_ids(materials, completed)  # T6.5, computed once instead of per tile
    # BUS-008: group by the chapters materials actually have, not CHAPTER_CHOICES, so an unlisted
    # chapter value can never hide an active material. Empty chapters simply don't appear.
    names = dict(Material.CHAPTER_CHOICES)
    chapters = []
    for number, group in groupby(materials, key=attrgetter("chapter")):
        group = list(group)
        rows = [(m, progress.get(m.id), m.id in quiz_material_ids, m.id in locked) for m in group]
        done = sum(1 for _, p, _, _ in rows if p and p.status == JoinerProgress.COMPLETED)
        chapters.append({"number": number, "name": names.get(number, f"Chapter {number}"),
                         "rows": rows, "done": done})
    return render(request, "checklist.html", {"chapters": chapters})


@login_required
def material_view(request, pk):
    material = _open_material(request, pk)
    if material is None:
        return redirect("home")
    progress, _ = JoinerProgress.objects.get_or_create(user=request.user, material=material)
    has_quiz = hasattr(material, "quiz")

    # Viewing only marks progress; the joiner completes it by clicking "Mark complete"
    # (no-quiz) or passing the quiz.
    if progress.status == JoinerProgress.NOT_STARTED:
        progress.status = JoinerProgress.VIEWED
        progress.save()

    return render(
        request,
        "material.html",
        {"material": material, "progress": progress, "has_quiz": has_quiz,
         "file_url": material.source_url},  # file: presigned 15-min, type forced (SEC-020) · link: as-is
    )


@login_required
@require_POST
def mark_complete(request, pk):
    material = _open_material(request, pk)
    if material is None:
        return redirect("home")
    if hasattr(material, "quiz"):
        raise Http404("quiz materials complete via the quiz")  # can't shortcut the quiz gate
    # BUS-005: the "reviewed" gate is client-side, so at minimum require a real
    # material_view hit first — no progress row (never opened) => 404, not a free completion.
    progress = get_object_or_404(JoinerProgress, user=request.user, material=material)
    if progress.status == JoinerProgress.VIEWED:
        progress.status = JoinerProgress.COMPLETED
        progress.completed_at = timezone.now()
        progress.save()
    return redirect("home")  # already completed -> idempotent no-op


@login_required
def quiz(request, pk):
    material = _open_material(request, pk)
    if material is None:
        return redirect("home")
    if not hasattr(material, "quiz"):
        raise Http404("no quiz for this material")
    quiz_obj = material.quiz
    questions = list(quiz_obj.questions.prefetch_related("choices"))

    if request.method != "POST":
        return render(request, "quiz.html", {"material": material, "questions": questions})

    # Score: one selected choice per question; correct if it is_correct. (Single-correct MVP.)
    total = len(questions)
    correct = 0
    for q in questions:
        selected = request.POST.get(f"q{q.id}")
        correct_ids = {str(c.id) for c in q.choices.all() if c.is_correct}
        if selected in correct_ids:
            correct += 1
    score = round(correct / total * 100) if total else 0  # ponytail: empty quiz -> 0, can't pass
    passed = total > 0 and score >= quiz_obj.pass_mark

    progress, _ = JoinerProgress.objects.get_or_create(user=request.user, material=material)
    # BUS-003: once completed, a failing retake must not downgrade the passing record.
    if not (progress.status == JoinerProgress.COMPLETED and not passed):
        now = timezone.now()
        progress.score = score
        progress.passed = passed
        progress.submitted_at = now
        if passed:
            progress.status = JoinerProgress.COMPLETED
            progress.completed_at = now
        elif progress.status == JoinerProgress.NOT_STARTED:
            progress.status = JoinerProgress.VIEWED  # failed retake still counts as viewed
        progress.save()

    return render(
        request,
        "result.html",
        {"material": material, "score": score, "passed": passed, "pass_mark": quiz_obj.pass_mark},
    )
