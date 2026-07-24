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
