"""One check per non-trivial path (T5.3): quiz scoring/state machine, presign URL shape, csv_safe.
No fixtures/frameworks — Django TestCase + the joiner flow. `manage.py test core`.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from .admin import _csv_safe
from .middleware import ADMIN_SESSION_COOKIE
from .models import Choice, JoinerProgress, Material, Question, Quiz

User = get_user_model()


def _admin_login(client, user):
    # T6.6: force_login sets the frontend cookie; /admin/ only reads its own.
    client.force_login(user)
    client.cookies[ADMIN_SESSION_COOKIE] = client.cookies.pop("sessionid").value


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

    def test_image_upload_checks_extension_and_header(self):
        # T6.11: only real JPEG/PNG bytes behind a matching extension; served with a forced image type.
        from django.core.files.uploadedfile import SimpleUploadedFile

        def clean(name, data):
            Material(title="I", type=Material.IMAGE, file=SimpleUploadedFile(name, data)).full_clean()

        clean("a.jpg", b"\xff\xd8\xff\xe0rest")
        clean("a.PNG", b"\x89PNG\r\n\x1a\nrest")
        for name, data in (("a.html", b"\xff\xd8\xff"), ("a.jpg", b"<html>"), ("a.png", b"\xff\xd8\xff")):
            with self.assertRaises(ValidationError):
                clean(name, data)
        img = Material(title="I", type=Material.IMAGE, file="materials/a.png")
        self.assertIn("response-content-type=image%2Fpng", img.source_url)

    def test_file_extension_must_match_type(self):
        # ROB-012: switching type can't keep the wrong file.
        for type_, name in ((Material.PDF, "a.png"), (Material.VIDEO, "a.pdf"), (Material.IMAGE, "a.pdf")):
            with self.assertRaises(ValidationError):
                Material(title="M", type=type_, file=f"materials/{name}").full_clean()
        Material(title="V", type=Material.VIDEO, file="materials/a.MP4").full_clean()
        # T6.14: video accepts a URL instead of a file (embedded like a Link), but needs one of the two.
        url_video = Material(title="V", type=Material.VIDEO, url="https://youtu.be/tUd9Dg0R9CA")
        url_video.full_clean()
        self.assertEqual(url_video.source_url, "https://www.youtube.com/embed/tUd9Dg0R9CA")
        with self.assertRaisesMessage(ValidationError, "Video materials need a file or a URL."):
            Material(title="V", type=Material.VIDEO).full_clean()
        with self.assertRaises(ValidationError):
            Material(title="P", type=Material.PDF, url="https://example.com/a.pdf").full_clean()
        with self.assertRaisesMessage(ValidationError, "Image materials must be a .jpg, .jpeg or .png file."):
            Material(title="I", type=Material.IMAGE, file="materials/a.gif").full_clean()

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

    def test_locked_button_explains_itself(self):
        # COM-008
        resp = self.client.get(reverse("material", args=[self.material.pk]))
        self.assertContains(resp, 'aria-describedby="mc-hint"')
        self.assertContains(resp, "Watch the video to the end to enable")

    def test_image_alt_uses_description_else_title(self):
        # COM-022
        img = Material.objects.create(title="Org chart", type=Material.IMAGE, file="materials/o.png")
        self.assertContains(self.client.get(reverse("material", args=[img.pk])), 'alt="Org chart"')
        # ROB-017: a failed image must hide the "Loading" dots (failed lives in the card scope the hint reads)
        resp = self.client.get(reverse("material", args=[img.pk]))
        self.assertContains(resp, 'x-data="{ reviewed: false, failed: false }"')
        self.assertContains(resp, 'x-show="!reviewed && !failed"')
        img.description = "CEO at top, three teams below"
        img.save()
        self.assertContains(self.client.get(reverse("material", args=[img.pk])), 'alt="CEO at top, three teams below"')

    def test_pdf_viewer_region_without_open_link(self):
        # COM-007a region stays; COM-007b "Open PDF in browser viewer" link removed on request (2026-09-15).
        # Forced application/pdf on the URL is covered by test_file_urls_force_safe_response_type (SEC-020).
        pdf = Material.objects.create(title="Doc", type=Material.PDF, file="materials/x.pdf")
        resp = self.client.get(reverse("material", args=[pdf.pk]))
        self.assertNotContains(resp, "Open PDF in browser viewer")
        self.assertContains(resp, 'role="region"')

    def test_file_urls_force_safe_response_type(self):
        # SEC-020: a disguised HTML upload must never render as a same-origin page.
        pdf = Material(title="P", type=Material.PDF, file="materials/x.pdf")
        video = Material(title="V", type=Material.VIDEO, file="materials/v.mp4")
        self.assertIn("response-content-type=application%2Fpdf", pdf.source_url)
        self.assertIn("response-content-disposition=attachment", video.source_url)

    def test_fileless_material_redirects_home_not_500(self):
        # ROB-005
        empty = Material.objects.create(title="Empty", type=Material.PDF, file="")
        for name in ("material", "mark_complete", "quiz"):
            resp = self.client.get(reverse(name, args=[empty.pk])) if name == "material" else \
                self.client.post(reverse(name, args=[empty.pk]))
            self.assertRedirects(resp, reverse("home"), fetch_redirect_response=False)


@override_settings(SECURE_SSL_REDIRECT=False)
class TopbarProgressTests(TestCase):
    def test_counts_only_active_materials_for_this_joiner(self):
        user = User.objects.create_user("j9", password="pw-testing-123")
        other = User.objects.create_user("j10", password="pw-testing-123")
        self.client.force_login(user)
        a = Material.objects.create(title="A", type=Material.LINK, url="https://x.test")
        Material.objects.create(title="B", type=Material.LINK, url="https://x.test")
        gone = Material.objects.create(title="Old", type=Material.LINK, url="https://x.test", is_active=False)
        JoinerProgress.objects.create(user=user, material=a, status=JoinerProgress.COMPLETED)
        JoinerProgress.objects.create(user=user, material=gone, status=JoinerProgress.COMPLETED)
        JoinerProgress.objects.create(user=other, material=a, status=JoinerProgress.COMPLETED)
        resp = self.client.get(reverse("home"))
        self.assertEqual(resp.context["topbar"], {"done": 1, "total": 2, "ratio": 0.5})
        self.assertContains(resp, "1 of 2 complete")
        self.assertContains(resp, "--p:0.500")
        self.assertNotContains(resp, 'id="congrats"')
        # T6.8: congratulations popup only once every active material is complete.
        JoinerProgress.objects.create(user=user, material=Material.objects.get(title="B"),
                                      status=JoinerProgress.COMPLETED)
        self.assertContains(self.client.get(reverse("home")), 'id="congrats"')


@override_settings(SECURE_SSL_REDIRECT=False)
class ChecklistChapterTests(TestCase):
    def test_materials_grouped_by_chapter_with_counts(self):
        user = User.objects.create_user("j3", password="pw-testing-123")
        self.client.force_login(user)
        sec = Material.objects.create(title="Phishing", type=Material.LINK, url="https://x.test", chapter=2)
        info = Material.objects.create(title="Handbook", type=Material.LINK, url="https://x.test")  # default ch 1
        JoinerProgress.objects.create(user=user, material=sec, status=JoinerProgress.COMPLETED)
        chapters = self.client.get(reverse("home")).context["chapters"]
        self.assertEqual([(c["number"], [r[0] for r in c["rows"]], c["done"]) for c in chapters],
                         [(1, [info], 0), (2, [sec], 1)])
        # BUS-008: a chapter value outside CHAPTER_CHOICES must still render, not vanish.
        stray = Material.objects.create(title="Stray", type=Material.LINK, url="https://x.test", chapter=9)
        chapters = self.client.get(reverse("home")).context["chapters"]
        self.assertEqual((chapters[-1]["name"], [r[0] for r in chapters[-1]["rows"]]), ("Chapter 9", [stray]))


@override_settings(SECURE_SSL_REDIRECT=False)
class LockedMaterialTests(TestCase):
    def test_locked_until_other_materials_completed(self):
        user = User.objects.create_user("j4", password="pw-testing-123")
        self.client.force_login(user)
        intro = Material.objects.create(title="Intro", type=Material.LINK, url="https://x.test")
        final = Material.objects.create(title="Final", type=Material.LINK, url="https://x.test", locked=True)
        also_locked = Material.objects.create(title="Also", type=Material.LINK, url="https://x.test", locked=True)
        Material.objects.create(title="Retired", type=Material.LINK, url="https://x.test", is_active=False)
        Quiz.objects.create(material=final)

        rows = self.client.get(reverse("home")).context["chapters"][0]["rows"]
        self.assertEqual([(r[0], r[3]) for r in rows], [(intro, False), (final, True), (also_locked, True)])
        # Every endpoint is gated server-side, not just hidden on the checklist.
        self.assertEqual(self.client.get(reverse("material", args=[final.pk])).status_code, 302)
        self.assertEqual(self.client.post(reverse("quiz", args=[final.pk]), {}).status_code, 302)
        self.assertEqual(self.client.post(reverse("mark_complete", args=[also_locked.pk])).status_code, 302)
        self.assertFalse(JoinerProgress.objects.filter(material__locked=True).exists())

        # Completing the unlocked one opens both locked ones (inactive + locked never block),
        # and an unfinished material in another chapter doesn't block chapter 1.
        Material.objects.create(title="Ch2", type=Material.LINK, url="https://x.test", chapter=2)
        JoinerProgress.objects.create(user=user, material=intro, status=JoinerProgress.COMPLETED)
        rows = self.client.get(reverse("home")).context["chapters"][0]["rows"]
        self.assertEqual([r[3] for r in rows], [False, False, False])
        self.assertFalse(final.is_locked_for(user))
        self.assertEqual(self.client.get(reverse("material", args=[final.pk])).status_code, 200)

        # BUS-009: once completed, a newly added unlocked material doesn't re-lock it.
        JoinerProgress.objects.filter(user=user, material=final).update(status=JoinerProgress.COMPLETED)
        Material.objects.create(title="New", type=Material.LINK, url="https://x.test")
        self.assertFalse(final.is_locked_for(user))
        rows = self.client.get(reverse("home")).context["chapters"][0]["rows"]
        self.assertEqual([r[3] for r in rows if r[0] == final], [False])


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

    def test_login_error_is_announced(self):
        # COM-011
        resp = self.client.post(reverse("login"), {"username": "nobody", "password": "wrong-pass-123"})
        self.assertContains(resp, 'role="alert"')

    def test_joiner_allowed_at_frontend_login(self):
        User.objects.create_user("joiner", password="pw-testing-123")
        resp = self.client.post(reverse("login"), {"username": "joiner", "password": "pw-testing-123"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)


@override_settings(SECURE_SSL_REDIRECT=False)
class JoinerAdminTests(TestCase):
    def setUp(self):
        _admin_login(self.client, User.objects.create_superuser("hr2", password="pw-testing-123"))
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

    def test_export_needs_progress_permission(self):
        # SEC-012: view_joiner alone must not hand over everyone's progress rows, and the
        # denial must land before the pk lookup so 403-vs-404 isn't an existence oracle.
        clerk = User.objects.create_user("clerk", password="pw-testing-123", is_staff=True)
        clerk.user_permissions.add(Permission.objects.get(codename="view_joiner"))
        _admin_login(self.client, clerk)
        joiner = User.objects.get(username="aaa")
        self.assertEqual(self.client.get(reverse("admin:core_joiner_export")).status_code, 403)
        self.assertEqual(
            self.client.get(reverse("admin:core_joiner_export_one", args=[joiner.pk])).status_code, 403)
        self.assertEqual(
            self.client.get(reverse("admin:core_joiner_export_one", args=[999999])).status_code, 403)

    def test_export_survives_a_bad_filter_value(self):
        # SEC-013: IncorrectLookupParameters used to escape as a 500.
        resp = self.client.get(reverse("admin:core_joiner_export") + "?is_active__exact=bogus")
        self.assertRedirects(resp, reverse("admin:core_joiner_changelist"))


@override_settings(SECURE_SSL_REDIRECT=False)
class OldProgressUrlRedirectTests(TestCase):
    def test_old_progress_admin_urls_redirect_to_joiners(self):
        _admin_login(self.client, User.objects.create_superuser("hr3", password="pw-testing-123"))
        for old in ("/admin/core/joinerprogress/", "/admin/core/joinerprogress/26/change/?_facets=True"):
            resp = self.client.get(old)
            self.assertRedirects(resp, reverse("admin:core_joiner_changelist"), status_code=301)


@override_settings(SECURE_SSL_REDIRECT=False)
class SessionIsolationTests(TestCase):
    def test_admin_and_frontend_sessions_are_independent(self):
        User.objects.create_superuser("hr4", password="pw-testing-123")
        User.objects.create_user("j4", password="pw-testing-123")
        self.client.post(reverse("admin:login"), {"username": "hr4", "password": "pw-testing-123"})
        self.assertIn(ADMIN_SESSION_COOKIE, self.client.cookies)
        self.assertNotIn("sessionid", self.client.cookies)
        self.assertEqual(self.client.get(reverse("home")).status_code, 302)  # admin login ≠ frontend login

        self.client.post(reverse("login"), {"username": "j4", "password": "pw-testing-123"})
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)  # admin still in

        self.client.post(reverse("logout"))  # frontend logout leaves admin alone
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)
        self.assertEqual(self.client.get(reverse("home")).status_code, 302)

        # A frontend cookie must never authenticate /admin/.
        self.client.cookies.pop(ADMIN_SESSION_COOKIE)
        self.client.post(reverse("login"), {"username": "j4", "password": "pw-testing-123"})
        self.client.cookies["sessionid"] = self.client.cookies["sessionid"].value
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 302)

    def test_admin_login_page_creates_no_session_row(self):
        # ROB-001: anonymous GETs (healthcheck hits /admin/login/ every 10s) must not write sessions.
        from django.contrib.sessions.models import Session
        self.client.get(reverse("admin:login"))
        self.client.get(reverse("login"))
        self.assertEqual(Session.objects.count(), 0)

    def test_admin_has_no_view_site_link(self):
        # BUS-013
        _admin_login(self.client, User.objects.create_superuser("hr5", password="pw-testing-123"))
        self.assertNotContains(self.client.get(reverse("admin:index")), "View site")
