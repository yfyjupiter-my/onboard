import os
from urllib.parse import parse_qs, urlparse

from django.conf import settings
from django.contrib.auth.models import User
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
    IMAGE = "image"
    TYPE_CHOICES = [(PDF, "PDF"), (VIDEO, "Video"), (LINK, "Link"), (IMAGE, "Image")]
    # T6.11: extension -> (magic bytes, served Content-Type). The header check stops a renamed HTML/SVG upload.
    IMAGE_FORMATS = {
        ".jpg": (b"\xff\xd8\xff", "image/jpeg"),
        ".jpeg": (b"\xff\xd8\xff", "image/jpeg"),
        ".png": (b"\x89PNG\r\n\x1a\n", "image/png"),
    }
    # ponytail: fixed list; promote to a Chapter model if HR needs to add/rename chapters themselves.
    CHAPTER_CHOICES = [(1, "Internal information"), (2, "Security awareness")]

    title = models.CharField(max_length=200)
    chapter = models.PositiveSmallIntegerField(choices=CHAPTER_CHOICES, default=1)
    type = models.CharField(max_length=5, choices=TYPE_CHOICES)
    file = models.FileField(upload_to="materials/", blank=True)  # blank for LINK; PDF/video/image need one
    url = models.URLField(blank=True)  # LINK only; embedded in an iframe
    is_active = models.BooleanField(default=True)
    locked = models.BooleanField(
        "locked until the rest of its chapter is completed", default=False,
        help_text="Joiners can only open this once every other active, unlocked material in the same chapter is completed.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.type == self.LINK and not self.url:
            raise ValidationError({"url": "Link materials need a URL."})
        if self.type != self.LINK and not self.file:
            raise ValidationError({"file": "PDF, video and image materials need a file."})
        if self.type == self.IMAGE and self.file:
            fmt = self.image_format
            if not fmt:
                raise ValidationError({"file": "Image materials must be a .jpg, .jpeg or .png file."})
            if not self.file._committed:  # new upload only; don't re-download stored files on every save
                self.file.seek(0)
                head = self.file.read(len(fmt[0]))
                self.file.seek(0)
                if head != fmt[0]:
                    raise ValidationError({"file": "This file isn't a real JPEG/PNG image."})

    @property
    def image_format(self):
        return self.IMAGE_FORMATS.get(os.path.splitext(self.file.name)[1].lower())  # (magic, content type) or None

    @property
    def source_url(self):
        if self.type == self.LINK:
            return embeddable(self.url)
        # SEC-020: never let an upload render as a same-origin page, whatever its stored type.
        # PDF.js and <video> ignore these overrides; a direct top-level visit gets a PDF / a download.
        if self.type == self.PDF:
            params = {"ResponseContentType": "application/pdf"}
        elif self.type == self.IMAGE:
            fmt = self.image_format
            params = ({"ResponseContentType": fmt[1]} if fmt else {"ResponseContentDisposition": "attachment"})
        else:
            params = {"ResponseContentDisposition": "attachment"}
        return self.file.storage.url(self.file.name, parameters=params)

    def is_locked_for(self, user):
        # T6.5: locked materials wait on every active, *unlocked* material in the same chapter
        # (locked ones never block each other, so two locked materials can't deadlock).
        if not self.locked:
            return False
        done = JoinerProgress.objects.filter(user=user, status=JoinerProgress.COMPLETED)
        if done.filter(material=self).exists():
            return False  # BUS-009: already completed stays open when new materials are added
        return (Material.objects.filter(is_active=True, locked=False, chapter=self.chapter)
                .exclude(pk__in=done.values("material_id")).exists())

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


class Joiner(User):
    # Proxy of User so the admin can list progress once per joiner instead of one row
    # per (user, material) pair. No columns of its own.
    class Meta:
        proxy = True
        verbose_name = "joiner"
