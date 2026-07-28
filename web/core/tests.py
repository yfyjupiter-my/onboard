"""One check per non-trivial path (T5.3): quiz scoring/state machine, presign URL shape, csv_safe.
No fixtures/frameworks — Django TestCase + the joiner flow. `manage.py test core`.
"""
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from .admin import _csv_safe
from .models import Choice, JoinerProgress, Material, Question, Quiz

User = get_user_model()


class CsvSafeTests(TestCase):
    def test_formula_prefixes_are_quoted(self):
        for danger in ("=1+2", "+1", "-1", "@cmd", "\tx", "\rx"):
            self.assertEqual(_csv_safe(danger), "'" + danger)

    def test_benign_values_untouched(self):
        self.assertEqual(_csv_safe("Alice"), "Alice")
        self.assertEqual(_csv_safe("a@b.com"), "a@b.com")  # only leading @ is dangerous
        self.assertEqual(_csv_safe(None), "")
        self.assertEqual(_csv_safe(90), "90")


# Prod defaults 301-redirect plain http to https; test client sends http, so bypass for view tests.
@override_settings(SECURE_SSL_REDIRECT=False)
class QuizFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("joiner", password="pw-testing-123")
        self.client.force_login(self.user)
        self.material = Material.objects.create(title="Handbook", type=Material.PDF, file="materials/x.pdf")
        self.quiz = Quiz.objects.create(material=self.material, pass_mark=80)
        # 2 questions, each 1 correct choice.
        self.answers = {}
        for i in range(2):
            q = Question.objects.create(quiz=self.quiz, text=f"Q{i}", order=i)
            right = Choice.objects.create(question=q, text="right", is_correct=True)
            Choice.objects.create(question=q, text="wrong", is_correct=False)
            self.answers[f"q{q.id}"] = str(right.id)

    def _submit(self, post):
        return self.client.post(reverse("quiz", args=[self.material.pk]), post)

    def test_all_correct_passes_and_completes(self):
        self._submit(self.answers)
        p = JoinerProgress.objects.get(user=self.user, material=self.material)
        self.assertEqual(p.score, 100)
        self.assertTrue(p.passed)
        self.assertEqual(p.status, JoinerProgress.COMPLETED)
        self.assertIsNotNone(p.completed_at)

    def test_half_correct_fails_stays_viewed(self):
        post = dict(self.answers)
        post[list(self.answers)[0]] = "999999"  # one wrong
        self._submit(post)
        p = JoinerProgress.objects.get(user=self.user, material=self.material)
        self.assertEqual(p.score, 50)
        self.assertFalse(p.passed)
        self.assertEqual(p.status, JoinerProgress.VIEWED)

    def test_failing_retake_after_completion_keeps_pass(self):
        # BUS-003: pass, then fail on retake — passing record must survive.
        self._submit(self.answers)
        wrong = {k: "999999" for k in self.answers}
        self._submit(wrong)
        p = JoinerProgress.objects.get(user=self.user, material=self.material)
        self.assertEqual(p.status, JoinerProgress.COMPLETED)
        self.assertTrue(p.passed)
        self.assertEqual(p.score, 100)


@override_settings(SECURE_SSL_REDIRECT=False)
class ModelValidationTests(TestCase):
    def test_pass_mark_over_100_rejected(self):
        m = Material.objects.create(title="M", type=Material.PDF, file="materials/x.pdf")
        with self.assertRaises(ValidationError):
            Quiz(material=m, pass_mark=150).full_clean()

    def test_link_material_requires_url_and_serves_it(self):
        with self.assertRaises(ValidationError):
            Material(title="L", type=Material.LINK).full_clean()
        with self.assertRaises(ValidationError):
            Material(title="P", type=Material.PDF).full_clean()
        link = Material(title="L", type=Material.LINK, url="https://example.com/handbook")
        link.full_clean()
        self.assertEqual(link.source_url, "https://example.com/handbook")

    def test_youtube_links_rewritten_to_embed(self):
        embed = "https://www.youtube.com/embed/tUd9Dg0R9CA"
        for url in ("https://www.youtube.com/watch?v=tUd9Dg0R9CA",
                    "https://youtube.com/watch?v=tUd9Dg0R9CA&t=30",
                    "https://youtu.be/tUd9Dg0R9CA"):
            self.assertEqual(Material(type=Material.LINK, url=url).source_url, embed)
        # Not YouTube, or no video id -> untouched.
        for url in ("https://example.com/watch?v=x", "https://www.youtube.com/watch"):
            self.assertEqual(Material(type=Material.LINK, url=url).source_url, url)


class ChoiceFormSetTests(TestCase):
    # BUS-001: exactly one correct choice per question.
    def setUp(self):
        m = Material.objects.create(title="M", type=Material.PDF, file="materials/x.pdf")
        quiz = Quiz.objects.create(material=m)
        self.question = Question.objects.create(quiz=quiz, text="Q")

    def _formset(self, correct_flags):
        from django.forms.models import inlineformset_factory

        from .admin import ChoiceInlineFormSet
        FS = inlineformset_factory(Question, Choice, formset=ChoiceInlineFormSet,
                                   fields=["text", "is_correct"], extra=0)
        data = {"choices-TOTAL_FORMS": str(len(correct_flags)),
                "choices-INITIAL_FORMS": "0", "choices-MIN_NUM_FORMS": "0",
                "choices-MAX_NUM_FORMS": "1000"}
        for i, flag in enumerate(correct_flags):
            data[f"choices-{i}-text"] = f"c{i}"
            if flag:
                data[f"choices-{i}-is_correct"] = "on"
        return FS(data, instance=self.question)

    def test_exactly_one_correct_valid(self):
        self.assertTrue(self._formset([True, False]).is_valid())

    def test_zero_correct_invalid(self):
        self.assertFalse(self._formset([False, False]).is_valid())

    def test_two_correct_invalid(self):
        self.assertFalse(self._formset([True, True]).is_valid())


@override_settings(SECURE_SSL_REDIRECT=False)
class NoQuizViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("j2", password="pw-testing-123")
        self.client.force_login(self.user)
        self.material = Material.objects.create(title="Video", type=Material.VIDEO, file="materials/v.mp4")

    def test_viewing_only_marks_in_progress(self):
        self.client.get(reverse("material", args=[self.material.pk]))
        p = JoinerProgress.objects.get(user=self.user, material=self.material)
        self.assertEqual(p.status, JoinerProgress.VIEWED)

    def test_mark_complete_button_completes(self):
        self.client.get(reverse("material", args=[self.material.pk]))  # must open it first
        self.client.post(reverse("mark_complete", args=[self.material.pk]))
        p = JoinerProgress.objects.get(user=self.user, material=self.material)
        self.assertEqual(p.status, JoinerProgress.COMPLETED)
        self.assertIsNotNone(p.completed_at)

    def test_mark_complete_rejects_unopened_material(self):
        # BUS-005: no progress row means the joiner never opened it — no free completion.
        resp = self.client.post(reverse("mark_complete", args=[self.material.pk]))
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(JoinerProgress.objects.filter(user=self.user).exists())

    def test_mark_complete_rejects_quiz_material(self):
        Quiz.objects.create(material=self.material, pass_mark=80)
        resp = self.client.post(reverse("mark_complete", args=[self.material.pk]))
        self.assertEqual(resp.status_code, 404)


class PresignTests(TestCase):
    def test_file_url_is_presigned_and_scoped_to_media(self):
        material = Material.objects.create(title="Doc", type=Material.PDF, file="materials/x.pdf")
        url = material.file.url
        self.assertIn("/media/", url)          # bucket segment rewritten (T2.2)
        self.assertIn("X-Amz-Signature", url)  # signed, not public
        self.assertIn("X-Amz-Expires=900", url)


@override_settings(SECURE_SSL_REDIRECT=False)
class JoinerLoginFormTests(TestCase):
    def test_staff_rejected_at_frontend_login(self):
        User.objects.create_user("hr", password="pw-testing-123", is_staff=True)
        resp = self.client.post(reverse("login"), {"username": "hr", "password": "pw-testing-123"})
        self.assertEqual(resp.status_code, 200)  # re-rendered, not logged in
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_joiner_allowed_at_frontend_login(self):
        User.objects.create_user("joiner", password="pw-testing-123")
        resp = self.client.post(reverse("login"), {"username": "joiner", "password": "pw-testing-123"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)


@override_settings(SECURE_SSL_REDIRECT=False)
class JoinerAdminTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser("hr2", password="pw-testing-123"))
        material = Material.objects.create(title="Doc", type=Material.PDF, file="materials/x.pdf")
        Material.objects.create(title="Doc 2", type=Material.PDF, file="materials/y.pdf")
        for name in ("aaa", "bbb"):
            JoinerProgress.objects.create(
                user=User.objects.create_user(name), material=material,
                status=JoinerProgress.COMPLETED, score=90, passed=True,
            )

    def test_changelist_lists_each_joiner_once_with_counts(self):
        resp = self.client.get(reverse("admin:core_joiner_changelist"))
        self.assertEqual(resp.content.count(b'class="field-completed"'), 2)  # one row per joiner
        self.assertContains(resp, "1 / 2")  # completed / active materials
        self.assertContains(resp, "2 joiners")  # staff (hr2) excluded from the list

    def test_change_view_shows_progress_rows(self):
        joiner = User.objects.get(username="aaa")
        resp = self.client.get(reverse("admin:core_joiner_change", args=[joiner.pk]))
        self.assertContains(resp, "Doc")

    def test_export_button_exports_all(self):
        resp = self.client.get(reverse("admin:core_joiner_export"))
        self.assertEqual(resp["Content-Type"], "text/csv")
        self.assertEqual(len(resp.content.decode().strip().splitlines()), 3)  # header + 2

    def test_export_respects_changelist_filters(self):
        resp = self.client.get(reverse("admin:core_joiner_export") + "?q=aaa")
        self.assertEqual(len(resp.content.decode().strip().splitlines()), 2)  # header + 1

    def test_export_one_joiner(self):
        joiner = User.objects.get(username="aaa")
        resp = self.client.get(reverse("admin:core_joiner_export_one", args=[joiner.pk]))
        self.assertEqual(len(resp.content.decode().strip().splitlines()), 2)  # header + that joiner
        detail = self.client.get(reverse("admin:core_joiner_change", args=[joiner.pk]))
        self.assertContains(detail, "Export CSV")

    def test_export_button_rendered_on_changelist(self):
        resp = self.client.get(reverse("admin:core_joiner_changelist"))
        self.assertContains(resp, "Export CSV")


@override_settings(SECURE_SSL_REDIRECT=False)
class OldProgressUrlRedirectTests(TestCase):
    def test_old_progress_admin_urls_redirect_to_joiners(self):
        self.client.force_login(User.objects.create_superuser("hr3", password="pw-testing-123"))
        for old in ("/admin/core/joinerprogress/", "/admin/core/joinerprogress/26/change/?_facets=True"):
            resp = self.client.get(old)
            self.assertRedirects(resp, reverse("admin:core_joiner_changelist"), status_code=301)
