from urllib.parse import parse_qs, urlparse

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.db import models


def embeddable(url):
    # YouTube /watch and youtu.be pages send X-Frame-Options: SAMEORIGIN and render blank
    # in an iframe; only /embed/<id> is frameable. Rewrite those, leave everything else alone.
    # ponytail: YouTube only — it's the one link HR actually pastes. Add Vimeo/Drive if asked.
    parts = urlparse(url)
    host = parts.netloc.removeprefix("www.")
    if host in ("youtube.com", "m.youtube.com") and parts.path == "/watch":
        video_id = parse_qs(parts.query).get("v", [""])[0]
    elif host == "youtu.be":
        video_id = parts.path.lstrip("/")
    else:
        return url
    return f"https://www.youtube.com/embed/{video_id}" if video_id else url


class Material(models.Model):
    PDF = "pdf"
    VIDEO = "video"
    LINK = "link"
    TYPE_CHOICES = [(PDF, "PDF"), (VIDEO, "Video"), (LINK, "Link")]

    title = models.CharField(max_length=200)
    type = models.CharField(max_length=5, choices=TYPE_CHOICES)
    file = models.FileField(upload_to="materials/", blank=True)  # blank for LINK
    url = models.URLField(blank=True)  # LINK only; embedded in an iframe
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.type == self.LINK and not self.url:
            raise ValidationError({"url": "Link materials need a URL."})
        if self.type != self.LINK and not self.file:
            raise ValidationError({"file": "PDF and video materials need a file."})

    @property
    def source_url(self):
        return embeddable(self.url) if self.type == self.LINK else self.file.url

    def __str__(self):
        return self.title


class Quiz(models.Model):
    # One optional quiz per material (P4).
    material = models.OneToOneField(Material, on_delete=models.CASCADE, related_name="quiz")
    pass_mark = models.PositiveIntegerField(default=80, validators=[MaxValueValidator(100)])  # percent, BUS-002

    class Meta:
        verbose_name_plural = "quizzes"

    def __str__(self):
        return f"Quiz: {self.material.title}"


class Question(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questions")
    text = models.CharField(max_length=500)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.text


class Choice(models.Model):
    # MVP assumption: exactly one is_correct=True per question (single-answer MC / true-false).
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="choices")
    text = models.CharField(max_length=300)
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return self.text


class JoinerProgress(models.Model):
    NOT_STARTED = "not_started"
    VIEWED = "viewed"
    COMPLETED = "completed"
    STATUS_CHOICES = [(NOT_STARTED, "Not started"), (VIEWED, "Viewed"), (COMPLETED, "Completed")]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="progress")
    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name="progress")
    status = models.CharField(max_length=11, choices=STATUS_CHOICES, default=NOT_STARTED)
    score = models.PositiveIntegerField(null=True, blank=True)
    passed = models.BooleanField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "material"], name="unique_user_material_progress"),
        ]
        verbose_name_plural = "joiner progress"

    def __str__(self):
        return f"{self.user} · {self.material} · {self.status}"
