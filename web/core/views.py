from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from .models import JoinerProgress, Material


@login_required
def checklist(request):
    # All active materials left-joined to this user's progress. No lazy create here
    # (progress rows are created on first material view, per P3/P5).
    progress = {p.material_id: p for p in request.user.progress.all()}
    rows = [
        (m, progress.get(m.id))
        for m in Material.objects.filter(is_active=True).order_by("created_at")
    ]
    return render(request, "checklist.html", {"rows": rows})


@login_required
def material_view(request, pk):
    material = get_object_or_404(Material, pk=pk, is_active=True)
    progress, _ = JoinerProgress.objects.get_or_create(user=request.user, material=material)
    has_quiz = hasattr(material, "quiz")

    if not has_quiz:
        # No quiz: viewing completes it.
        if progress.status != JoinerProgress.COMPLETED:
            progress.status = JoinerProgress.COMPLETED
            progress.completed_at = timezone.now()
            progress.save()
    elif progress.status == JoinerProgress.NOT_STARTED:
        progress.status = JoinerProgress.VIEWED
        progress.save()

    return render(
        request,
        "material.html",
        {"material": material, "progress": progress, "has_quiz": has_quiz,
         "file_url": material.file.url},  # presigned, 15-min
    )


@login_required
def quiz(request, pk):
    material = get_object_or_404(Material, pk=pk, is_active=True)
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
