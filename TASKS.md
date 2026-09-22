# TASKS

Derived from `finalize.md` (P1–P15). One phase = one audit gate. Phase 0 is scaffold only.
Status legend: ☐ todo · ◐ in-progress · ✅ done · 🚫 blocked. Assignee: `cc` (Claude Code) unless noted.

---

## Phase 0 — Scaffold (make the stack boot) — ✅ DONE
Goal: `docker compose up --build` serves an app on `http://localhost` with migrate + collectstatic + gunicorn green. No features yet.
Verified: web healthy (migrate ✅ collectstatic ✅ 130 files, ensure_bucket ✅ `onboard-media` created, gunicorn up); home 200 "Scaffold is live", admin 200, static/vendor 200; `ALLOWED_HOSTS` correctly 400s bad Host. nginx blocked only by host :80 in use (environment, not code).

- ✅ **T0.1** `web/Dockerfile` — python:3.12-slim, curl, install `requirements.txt`, ENTRYPOINT `entrypoint.sh`. (P15)
- ✅ **T0.2** `requirements.txt` pinned `==` — Django 5.2.4, gunicorn, psycopg[binary], dj-database-url, django-storages[s3], boto3, whitenoise. (P1, P15)
- ✅ **T0.3** `onboard/` project + `core/` app hand-scaffolded (settings/urls/wsgi + apps/models/admin/views/urls/migrations). (P3)
- ✅ **T0.4** `settings.py` env-driven — DATABASE_URL, DJANGO_DEBUG, SECRET_KEY (required), ALLOWED_HOSTS, whitenoise middleware + ManifestStaticFilesStorage, security keys (P12). No hardcoded secrets. (P8, P12)
- ✅ **T0.5** `entrypoint.sh` — `ensure_bucket` mgmt command then `exec "$@"` (compose runs migrate→collectstatic→gunicorn). Idempotent bucket via boto3 head/create. (P11)
- ✅ **T0.6** `nginx/default.conf` — `/media/` → `minio:9000/onboard-media/`, `/` → `web:8000` with X-Forwarded-Proto; whitenoise handles `/static/`. (P2, P8)
- ✅ **T0.7** `base.html` + `home.html`, vendored `htmx.min.js`/`alpine.min.js`, `hx-headers` CSRF on `<body>`. **Deviation:** hand-written `app.css` from DESIGN.md instead of Tailwind — keeps runtime fully offline (Play CDN would break that); less code, no build step. (P7, P9)
- ✅ **T0.8** `web/.dockerignore`, `web` healthcheck (curl `/admin/login/`), `.env.example` gained `MINIO_BUCKET` + `DJANGO_CSRF_TRUSTED_ORIGINS`.

**Gate:** run audit check (Security + Code Quality) before Phase 1. ⬅ NEXT

---

## Phase 1 — Data model + admin — ✅ DONE
Goal: HR/IT can manage content in Django admin. (P3, P4, P5, P6)
Verified: `makemigrations` → `0001_initial` (all 5 models); fresh DB `migrate` OK; `manage.py check` 0 issues.

- ✅ **T1.1** Models in `core/models.py`: Material, Quiz (1:1, pass_mark 80), Question/Choice (single-correct MVP, documented), JoinerProgress (unique (user, material), nullable score/passed/submitted_at/completed_at). (P4, P5, P6)
- ✅ **T1.2** Admin — MaterialAdmin (+QuizInline), QuizAdmin (+QuestionInline), QuestionAdmin (+ChoiceInline), JoinerProgressAdmin read-only (`has_add_permission=False`, all fields readonly). Joiners `is_staff=False` → no admin access (Django default). (P13 CSV export hook deferred to Phase 4.)
- ✅ **T1.3** `core/migrations/0001_initial.py` committed. Fresh DB migrates clean.
  - Note: file generated in-container is `root`-owned on host (no sudo to chown) — cosmetic, git-trackable.

**Gate:** audit check (Code Quality + Business Logic) before Phase 2. ⬅ NEXT

---

## Phase 2 — MinIO storage + presigned URLs — ✅ DONE
Goal: uploaded files stored in MinIO, served to browser via 15-min presigned `/media` URLs only. (P1, P2, P11)
Verified (in-container): upload lands in MinIO; `storage.url()` → `http://<host>/media/<key>?X-Amz-...&X-Amz-Expires=900`; unsigned GET → **403** (private), signed GET → **200** (signature verifies). `check` 0 issues.

- ✅ **T2.1** `STORAGES.default = core.storage.MinioMediaStorage` (django-storages 1.14 `S3Storage`); `AWS_S3_ENDPOINT_URL=http://minio:9000`, bucket from `MINIO_BUCKET`, path-style, private ACL, no-overwrite. Admin FileField uploads land in MinIO, no custom upload code. (P1)
- ✅ **T2.2** `MinioMediaStorage.url()` presigns via a **public-endpoint** client (`MINIO_PUBLIC_ENDPOINT`), expiry 900s, then rewrites bucket segment → `/media/`. nginx rewrites `/media/`→`/onboard-media/` + forwards `Host $host` so the signature verifies. **Resolves SEC-001.** (P2)
- ✅ **T2.3** `ensure_bucket` idempotent; now only creates on 404/NoSuchBucket, re-raises 403/other (**resolves CODE-002**). Bucket private (unsigned 403). No manual `mc`. (P11)

**Gate:** audit check (Security — presign/expiry/private bucket) — ✅ PASS.
Re-audit 2026-07-24 (post CODE-001 nginx templating): CODE-001 bucket drift resolved (`default.conf.template` + envsubst `${MINIO_BUCKET}`, single source of truth); **SEC-008 fixed** — `NGINX_ENVSUBST_FILTER=MINIO_BUCKET` so envsubst can't blank the presign-signing `Host $host` header. Carry-forward unchanged: SEC-004 (root creds → service account, Phase 5), SEC-005 (15-min bearer URLs, accepted). See `SEC-AUDIT.md` / `CODE-AUDIT.md`.

---

## Phase 3 — Joiner flow (auth → checklist → viewer → quiz) — ✅ DONE
Goal: a joiner logs in, sees their checklist, views a material, takes a quiz, completes. (P3, P4, P5, P6, P9)
Verified (Django test client, in-container): unauth `/`→302 `/login/`; login OK; no-quiz view→completed; quiz view→viewed; fail 50%→not passed/stays viewed; retake 100%→completed; checklist shows completed badges; joiner (`is_staff=False`) `/admin/`→302. `check` 0 issues.

- ✅ **T3.1** Django built-in `LoginView`/`LogoutView` (logout POST) + `registration/login.html`, shared `_topbar.html`. `@login_required` on all three joiner views. Unauth → login redirect. (P9)
- ✅ **T3.2** `checklist` view `/` → `checklist.html`: active materials left-joined to this user's progress (dict lookup, no lazy create here); done/in-progress/not-started badges. (P3)
- ✅ **T3.3** `material_view` `/material/<id>/`: `get_or_create` progress; no-quiz → completed+completed_at; quiz + not_started → viewed. pdf `<iframe>` / video `<video controls>` `src=material.file.url` (presigned). (P5, P6)
- ✅ **T3.4** `quiz` `/material/<id>/quiz/`: GET renders radio questions; POST scores `round(correct/total*100)` from prefetched choices (no N+1), `passed = score>=pass_mark`, overwrites progress; unlimited retakes, no cooldown; empty-quiz guard →0. (P4)
- ✅ **T3.5** `result.html`: score, pass/fail, retake/back links. **Deviation:** plain POST `<form>` + `{% csrf_token %}` instead of htmx (native form is simpler; `hx-headers` still on `<body>` for future htmx). (P9)

**Gate:** audit check (Business Logic + Security) before Phase 4. ⬅ NEXT

---

## Phase 4 — HR/IT reporting — ✅ DONE
Goal: HR/IT exports progress. (P13)
Verified: `manage.py check` 0 issues in-container.

- ✅ **T4.1** Admin action "Export selected as CSV" on `JoinerProgress` — stdlib `csv` → `HttpResponse(text/csv)`, `select_related(user, material)`. Columns: joiner name (full name or username), email, material title, status, score, passed, completed_at (ISO). None → empty cell. (P13)

**Gate:** ✅ PASS — Compliance/Accessibility (`COM-AUDIT.md`) + CSV-injection (`SEC-AUDIT.md` SEC-007 fixed).

---

## Phase 5 — Hardening + docs — ✅ DONE
Goal: production security wiring + operator docs. (P10, P12, P14, P15)
Verified: `check --deploy` → only W009 (placeholder SECRET_KEY, operator value); `manage.py test core` 7/7 green.

- ✅ **T5.1** Security settings — already had CSRF_TRUSTED_ORIGINS, SECURE_PROXY_SSL_HEADER, SESSION/CSRF_COOKIE_SECURE, env ALLOWED_HOSTS, DEBUG=False default. Added prod-only (`if not DEBUG`) block: SECURE_SSL_REDIRECT + HSTS (1yr, subdomains, preload). Resolves SEC-003. (P12)
- ✅ **T5.2** `README.md` — configure `.env` table, `docker compose up --build`, `createsuperuser`, CSV export, prod notes (Cloudflare Access on `/admin/` per P14, SEC-004 service account), dev/test commands + rebuild note.
- ✅ **T5.3** `core/tests.py` — 7 tests: csv_safe (2), quiz scoring/state machine incl. BUS-003 (3), no-quiz completion (1), presign URL shape (1). No fixtures/framework bloat. `@override_settings(SECURE_SSL_REDIRECT=False)` on view tests (prod redirect vs http test client).

**Gate:** ✅ final audit PASS — 4 open items found & fixed (SEC-002 .gitignore, COM-003 local fonts, BUS-001 one-correct formset, BUS-002 pass_mark≤100). `test core` 11/11, `check --deploy` clean (W009 = placeholder key). Remaining are operator deploy steps (real secrets, git init, MinIO service account, Cloudflare Access) — no code blockers.
---

## Post-MVP — user-requested changes
Small changes requested after the 6 phases closed. Each is done + tested; no phase gate (no new attack surface beyond what the per-item audit notes cover).

- ✅ **T6.1** Material type **Link** — `Material.type` gains `link`; `url = URLField(blank=True)`, `file` now optional, `clean()` requires exactly one per type (admin-enforced), `source_url` returns the embeddable URL for links / presigned file URL otherwise. `embeddable()` (stdlib `urlparse`) rewrites `youtube.com/watch?v=` and `youtu.be/` → `/embed/<id>`. Rendered in a same-tab `<iframe>` that unlocks **Mark complete** on `load`; `referrerpolicy="strict-origin-when-cross-origin"` overrides Django's `same-origin` default so YouTube gets a `Referer` (its absence = YouTube error 153). Migration `0003_material_url` (additive). Checklist gets a link glyph.
  - **Known limit:** sites sending `X-Frame-Options`/frame-ancestors CSP render blank and this is undetectable cross-origin (the frame still fires `load`). The "Open link" fallback was removed by request → **prefer embeddable URLs** (YouTube, Drive `/preview`, intranet).
  - **Review gate is weak for links** (unlocks on frame load) — attach a quiz if proof of reading matters.
  - Acceptance: `manage.py test core` 18/18; browser-verified YouTube playback. Commit `d889f84`.

- ✅ **T6.2** Admin progress **grouped by joiner** — the flat one-row-per-(user, material) `JoinerProgress` changelist is replaced by a `Joiner` proxy model of `auth.User` (migration `0004_joiner`, no schema change). Changelist: one row per joiner (`is_staff=False`), columns joiner / email / `completed / active-materials` / last activity / active, all sortable; click through to a read-only `JoinerProgress` inline with material, status, score, passed, submitted/completed timestamps. Add + delete disabled (accounts stay in the Users admin). CSV export (T4.1, columns unchanged) moved to `admin:core_joiner_export`; it now exports the progress rows of the joiners matching the current search/filter. `JoinerProgress` unregistered from the admin index.
  - Old `/admin/core/joinerprogress/...` URLs 301 to the joiner changelist (`onboard/urls.py`, before `admin.site.urls`) so existing bookmarks/tabs keep working.
  - Acceptance: `manage.py test core` 24/24 (5 admin tests: one row per joiner + counts, detail inline, export all, export honours search, button rendered; + redirect test). Commit `c2335de`.

- ✅ **T6.3** **Per-joiner CSV export** — `admin:core_joiner_export_one` (`<int:pk>/export-csv/`) + "Export CSV" button in the joiner change-form toolbar (`templates/admin/core/joiner/change_form.html`). Reuses the T6.2 writer and columns. Staff pks 404 (admin queryset is joiners only).
  - Acceptance: `manage.py test core` 25/25. Commit `da914f6`.
  - **QA follow-up (`0fb743c`)** — SEC-012 all export paths require `view_joiner` + `view_joinerprogress`, checked before lookup (no 403/404 oracle); SEC-013 bad filter → 302 not 500; COM-004 every export logged; COM-005 README export/PII section. 27/27 tests. See `SEC-AUDIT.md` / `COM-AUDIT.md`.

- ✅ **T6.4** **Dashboard chapters** — `Material.chapter` (fixed choices: 1 · Internal information, 2 · Security awareness; default 1, so existing materials land in Chapter 1). Migration `0006_material_chapter` (additive). Admin: chapter column + filter. Checklist renders stacked sections per chapter (heading + "done / total" tag); empty chapters hidden; no locking (any order). Adding a chapter = one entry in `CHAPTER_CHOICES`.
  - Acceptance: `manage.py test core` 28/28 (new `ChecklistChapterTests`); `makemigrations --check` clean.

- ✅ **T6.5** **Locked materials** — `Material.locked` checkbox ("locked until the rest of its chapter is completed", default off). A locked material opens only once the joiner has completed every other active, unlocked material **in the same chapter** (locked ones never block each other → no deadlock; all-locked chapter = open). Enforced server-side in `material_view`, `mark_complete`, `quiz` (403 before any progress row is created), so typing the URL can't bypass it. Checklist shows a non-clickable tile with lock icon + "Locked · complete the rest of this chapter first". Admin: `locked` column + filter. Migration `0007_material_locked` (additive).
  - Acceptance: `manage.py test core` 29/29 (new `LockedMaterialTests`); `makemigrations --check` clean.

- ✅ **T6.6** **Isolated admin / frontend sessions** — `core/middleware.py` `SplitSessionMiddleware` (subclass of Django's `SessionMiddleware`, replaces it in `MIDDLEWARE`): `/admin/` uses its own cookie `admin_sessionid` (`Path=/admin/`), frontend keeps `sessionid`. The frontend cookie is stripped from admin requests, so it can never authenticate `/admin/`. CSRF stays cookie-based (`CSRF_USE_SESSIONS` was tried and removed by ROB-001: it wrote a session row for every anonymous login-page GET). Side effect: logging into one portal rotates the CSRF cookie, so a form already open in the other portal needs one reload. Logging in/out on one side leaves the other untouched.
  - QA fixes: ROB-001 dropped `CSRF_USE_SESSIONS` + `clearsessions` on `web` start + README daily cron; BUS-013 admin "View site" link hidden (`site_url = None`). 32/32 tests.
  - One-off: existing admin sessions (old `sessionid`) must sign in to `/admin/` again after deploy.
  - Acceptance: `manage.py test core` 30/30 (new `SessionIsolationTests`; admin tests use `_admin_login`); curl via nginx :8080 shows `admin_sessionid; Path=/admin/` vs `sessionid; Path=/`.

- ✅ **T6.7** **Top bar redesign (option B)** — picked from `topbar.html` playground. `_topbar.html`: full-bleed sticky edge bar (content aligned to `.wrap`), amber "Welcome back" kicker + username, "N of M complete" count, Log out with icon, 3px teal progress rail at the bottom edge. Motion: rail fills + check mark pings twice on load, bar slides away on scroll down / returns on scroll up (Alpine `@scroll.window`, stays visible while it holds focus). Count from `core/context_processors.py` `topbar_progress` (2 COUNT queries, active materials only; skipped for staff/anonymous so admin/login pay nothing). Count hidden <560px. Reduced-motion rule now also covers `::before/::after`.
  - Acceptance: `manage.py test core` 38/38 (new `TopbarProgressTests`); live checklist verified at 1280px + 390px, no horizontal scroll, hide/show on scroll.

- ✅ **T6.8** **Completion congratulations popup** — `checklist.html`: native `<dialog>` ("🎉 Congratulations, you did it! You've completed all your onboarding materials.") rendered only when `topbar.done == topbar.total > 0`, opened with `showModal()` (focus trap, Esc/Close). Shown once per browser via `localStorage` key `onboard-congrats-<user id>-<total>` (a newly added material earns a fresh popup; another device shows it again). No new query, model or dependency.
  - Acceptance: `manage.py test core` 38/38 (`TopbarProgressTests` asserts absent at 1/2, present at 2/2); Chromium 390px: opens on first visit, Esc closes, not shown on reload.

- ✅ **T6.9** **Ribbon burst on completion (option A)** — picked from the `ribbon.html` playground. When the T6.8 popup is due (all active materials complete, once per browser), `checklist.html` spawns 24 `aria-hidden` ribbons at the right end of the top bar's progress rail. They shoot out and flutter down (`tb-burst`, transform/opacity only), the check mark pops, and the popup opens at 1.5s. The ribbons are removed at 3.5s. Colours use existing tokens (primary, accent and their white mixes), with no new tokens. CSS in `app.css` (T6.9 block). Reduced motion: no ribbons, popup opens immediately.
  - Acceptance: `manage.py test core` 38/38; Chromium 1280px + 390px: 24 ribbons at 1.15s, popup open at 1.75s, ribbons gone at 4.2s, no horizontal scroll, no JS errors, nothing on reload; reduced motion opens the popup at 0.2s with 0 ribbons.

- ✅ **T6.10** **Link-material loading dots (option C)** — picked from the `mc-loading.html` playground. On link materials, the "Enables once the page has loaded" hint beside Mark complete is replaced by three bouncing teal dots (`#mc-hint.mc-dots`, `role="status"`), hidden by the existing `x-show="!reviewed"` once the frame loads. Screen readers still hear "Loading, Mark complete enables once the page has loaded" (`.sr-only`); the button keeps `aria-describedby="mc-hint"`. PDF/video hints unchanged (they tell the joiner what to do). CSS in `app.css` (T6.10 block), existing tokens only; reduced motion → static dots.
  - Acceptance: `manage.py test core` 38/38; rendered link page shows dots + sr text, PDF page still shows sentence.
  - QA follow-up: COM-020 accepted; ROB-009 fixed (iframe static `onload` sets `data-loaded`, `x-init` unlocks if the frame loaded before Alpine bound `@load`).
- ✅ **T6.11** **Image material type (JPEG + PNG)**: `Material.type` gains `image` ("Image" in the admin type dropdown). `clean()` accepts `.jpg`/`.jpeg`/`.png` only, and a new upload's first bytes must match (JPEG `FF D8 FF`, PNG signature), so a renamed HTML/SVG file is rejected. `source_url` presigns with a forced `image/jpeg` / `image/png` Content-Type (SEC-020 pattern). Joiner page: full-width `<img alt=title>`; Mark complete unlocks on `load`/`error` (with the ROB-009 onload flag) and shows the hint "Enables once the image has loaded". Checklist card gets an image icon. Migration `0008_material_type_image` (choices only, no schema change).
  - Acceptance: `manage.py test core` 39/39 (`test_image_upload_checks_extension_and_header`); a live PNG upload is served `200 image/png` via nginx presign.
- ✅ **T6.12** **Image QA follow-up (ROB-012, COM-022)**: `Material.clean()` checks the file extension against the type (PDF `.pdf`; video `.mp4/.webm/.mov`; image `.jpg/.jpeg/.png`), so switching type can't keep the wrong file. New optional `Material.description` ("image description", max 300) is used as `<img alt>`, falling back to the title. Migration `0009_material_description` (additive). COM-023 / BUS-020 accepted.
  - Acceptance: `manage.py test core` 40/40; all 17 live materials still pass `full_clean()`; migration 0009 applied on the live stack.
- ✅ **T6.13** **Image-material loading dots (option C, user request)** — the "Enables once the image has loaded" hint is replaced by the T6.10 `mc-dots` (same markup/CSS); sr text "Loading, Mark complete enables once the image has loaded". PDF/video hints unchanged.
  - Acceptance: `manage.py test core` green; rendered image page shows dots, no sentence.
- ✅ **T6.14** **Video material: file or URL (user request)** — `Material.clean()` lets a video have an uploaded file **or** a URL (error "Video materials need a file or a URL." when neither); PDF/image still need a file. New `Material.embeds_url` (Link, or video with no file): `source_url` returns the URL (YouTube rewritten to `/embed/`), joiner page renders it in the Link iframe with loading dots ("…once the video has loaded"). An uploaded file takes priority over the URL. Admin "Remove file" on a video with a URL keeps type Video (others still become Link). Migration `0011_material_url_help` (help text only).
- ✅ **T6.15** **Hide "Image description" in admin (user request)** — `MaterialAdmin.exclude = ("description",)` removes the row for all material types. Column and data kept (no migration); `<img alt>` still uses an existing description, else the title.
  - Acceptance: `manage.py test core` 41/41; `makemigrations --check` clean; URL-only video renders iframe, no `<video>`.
- ✅ **T6.16** **Joiner page lists incomplete materials (user request)** — `JoinerAdmin.incomplete_materials` read-only field on the joiner change page: every active material the joiner hasn't completed, in checklist order, with status ("Not started" also covers never-opened materials that have no progress row, which the progress inline can't show). Escaped via `format_html_join`. No migration.
  - Acceptance: `manage.py test core` 41/41 (`test_change_view_shows_progress_rows` asserts a never-opened material is listed and a completed one isn't).
  - Follow-up (user request): the per-material progress inline only had rows for opened materials, so it wasn't a full list. Replaced by a read-only `progress_table` field listing **every active material** (Material, Status, Score, Passed, Submitted at, Completed at); never-opened ones show "Not started" with blank cells. Inactive materials are not shown (CSV export still includes their rows). Tests 41/41; browser-verified on lily.chen (16 rows).

- ⚠️ **T6.17** **Give officekit its own Cloudflare Tunnel (operator, not code)** — onboard is published via a Cloudflare Tunnel (`prd.md` §Deployment): outbound-only `cloudflared`, zero inbound ports, Cloudflare terminates TLS at the edge and proxies to `nginx`. That is the *only* reason Cloudflare appears in this repo. On 2026-09-17 an unrelated project, `~/Documents/yfyjupiter/Integrations/officekit`, had onboard's `CLOUDFLARE_TUNNEL_TOKEN` copy-pasted into its `officekit-cloudflared-1` container, so two replicas joined the **same** tunnel; Cloudflare load-balanced `onboard.mymaples.com` across both and requests landing on the officekit replica (no route to onboard's nginx) timed out. Mitigated by `docker stop officekit-cloudflared-1` (stays down, `unless-stopped`).
  - Action Needed: issue officekit its **own** tunnel token + hostname in the Cloudflare dashboard, set it in `officekit/.env`, then `docker compose up -d cloudflared` there. Never reuse onboard's token. No change in this repo.
  - Acceptance: both hostnames resolve simultaneously from an off-LAN device; `cloudflared` journal shows no "no recent network activity" retries.

- ✅ **T6.18** **Kuala Lumpur timezone (user request)** — `TIME_ZONE = "Asia/Kuala_Lumpur"` in `web/onboard/settings.py` (`USE_TZ=True` unchanged, so Postgres keeps UTC and only rendering shifts): admin Joiners **Last Login / Completion** and the joiner detail timestamps show +08:00. Joiner CSV export writes `localtime(p.completed_at).isoformat()` (`web/core/admin.py`) instead of the stored UTC value. No migration; image rebuild required (code is baked in, restart alone keeps the old settings).
  - Acceptance: `manage.py test core` 44/44 (new `test_export_timestamps_are_local`: stored 00:30Z → `2026-09-22T08:30:00+08:00`); live DB check — `chris.goh` last login `2026-09-22 01:28Z` renders `Sept. 22, 2026, 9:28 a.m.`, export row shows `2026-09-14T15:49:45+08:00`.
