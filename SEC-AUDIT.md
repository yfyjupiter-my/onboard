# SEC-AUDIT — Security Vulnerabilities

## Phase 0 gate — 2026-07-24

Scope: scaffold only (settings, docker-compose, nginx, entrypoint, base template). No feature code yet.

SEC-001: nginx `/media/` presigned-URL signature will not verify
Verdict: ✅ Resolved in Phase 2 (T2.2) — see Phase 2 gate below. Verified: unsigned 403, signed 200.
Action Needed: nginx proxies `/media/<key>` → `minio:9000/onboard-media/<key>`, rewriting the path and forwarding `Host $host`. SigV4 signs the canonical path + host, so a URL signed against `<domain>/media/<key>` won't match what MinIO recomputes for `/onboard-media/<key>`. Presign must sign against the same host+path nginx sends (e.g. presign directly to the bucket path, or make the proxy preserve the signed URI), or every media fetch 403s. Not exploitable in Phase 0 (no uploads/presign yet) but the proxy is Phase 0 code — flag now.

SEC-002: `.env` with real secrets sits in project root, no `.gitignore`
Verdict: ⚠️ Pending
Action Needed: repo isn't git-initialized yet; before any `git init`, add `.gitignore` excluding `.env` (and `*.sqlite3`, `staticfiles/`). `web/.dockerignore` already excludes `.env`, so it's kept out of the image — this is only about future VCS leakage.

SEC-003: deploy-hardening headers absent (HSTS, SSL redirect)
Verdict: ⚠️ Pending (planned for Phase 5 / T5.1)
Action Needed: no `SECURE_HSTS_SECONDS`, `SECURE_SSL_REDIRECT`, `SECURE_HSTS_INCLUDE_SUBDOMAINS`. `manage.py check --deploy` will warn. Acceptable to defer to T5.1 as planned; not a Phase 0 blocker.

SEC-OK: verified-good (no action)
- No hardcoded secrets: `DJANGO_SECRET_KEY`, DB and MinIO creds are env-only; `SECRET_KEY` uses `os.environ[...]` (fails closed, no insecure fallback).
- `DEBUG` defaults False; `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE` on when not DEBUG.
- `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` env-driven; compose `:?` guards force `POSTGRES_PASSWORD`/`MINIO_ROOT_*`.
- web:8000 and minio not published; only nginx:80 exposed. No public MinIO bucket.
- CSRF middleware active; htmx CSRF token wired via `hx-headers` on `<body>`.

Gate verdict: PASS to Phase 1. No blocking vulnerability. SEC-001 is the one to not forget when Phase 2 lands.

---

## Phase 2 gate — 2026-07-24

Scope: `core/storage.py`, storage settings, `nginx/default.conf` `/media/` rewrite. Focus: presign / expiry / private bucket.

SEC-001 (resolved): presign now signed against the public host + bucket path; nginx rewrites `/media/`→`/onboard-media/` and forwards `Host $host`, so MinIO recomputes the same canonical request. Verified in-container: unsigned object GET **403**, signed GET **200**, `X-Amz-Expires=900`.

SEC-004: app signs objects with MinIO **root** credentials (least-privilege)
Verdict: ⚠️ Pending (hardening — defer to Phase 5 / T5.1)
Action Needed: `MinioMediaStorage` and `ensure_bucket` use `MINIO_ROOT_USER/PASSWORD`. A web-container compromise then yields full MinIO admin (all buckets, policy changes), not just `onboard-media`. Create a dedicated MinIO service account scoped to `onboard-media` (get/put/delete only) and give the app those keys; keep root creds for bootstrap only. Not a Phase 2 blocker (single bucket, MinIO not exposed), but the right hardening before prod.

SEC-005: presigned URLs are bearer tokens in the query string
Verdict: ✅ Acceptable (informational)
Action Needed: none for MVP. A `/media` URL grants read to anyone who has it for ≤15 min (it lands in Cloudflare/nginx access logs and browser history). Mitigated by the 900s expiry and low sensitivity (onboarding PDFs/MP4s). If truly sensitive material is ever added, shorten expiry / add per-user gating. No code change now.

SEC-OK: verified-good (no action)
- Bucket private: created with no anonymous policy; unsigned GET/list → 403. MinIO still unpublished (only nginx:80 exposed); no `AWS_S3_CUSTOM_DOMAIN` public-URL leak — every `.url()` is presigned (never unsigned).
- `url()` override cannot emit an unsigned URL; `AWS_DEFAULT_ACL=None` keeps objects private; `AWS_S3_FILE_OVERWRITE=False` avoids key-collision overwrite.
- nginx `/media/` can't escape the bucket: nginx normalizes `../` before location match, so `/media/../other` won't route here; ListObjects through the proxy still needs SigV4 → anonymous 403.
- Forged `Host` on `/media/` just breaks the attacker's own signature (403); no cache to poison.

Carry-forward (unchanged): SEC-002 (`.gitignore` for `.env` before `git init`), SEC-003 (HSTS/SSL-redirect → T5.1).

Gate verdict: PASS to Phase 3. No blocking vulnerability. SEC-004 is a pre-prod hardening item, not a blocker.

---

## Phase 3 gate — 2026-07-24

Scope: `core/views.py`, `core/urls.py`, auth + quiz templates. Focus: authz boundary, CSRF, injection, disclosure.

SEC-006: no login brute-force throttle
Verdict: ✅ Acceptable for MVP (defer — pairs with P14)
Action Needed: none in code now. `LoginView` has no rate limit/lockout; unlimited password guesses are possible. Intended mitigation is Cloudflare Access in front of the app (P14, README deploy step). If the app is ever exposed without Access, add `django-axes` or an nginx `limit_req` on `/login/`. Tracked, not a Phase 3 blocker.

SEC-OK: verified-good (no action)
- Authz: `@login_required` on all three joiner views; unauth `/` → 302 `/login/` (verified). Admin gated by `is_staff` — joiner (`is_staff=False`) `/admin/` → 302 (verified).
- No IDOR: quiz submit only touches `request.user`'s progress; material lookups are `is_active=True` only and every active material is intentionally visible to every joiner (P3).
- CSRF: `{% csrf_token %}` on login, quiz, and logout (logout is POST) forms; `CsrfViewMiddleware` active; `hx-headers` token on `<body>`.
- No XSS: all user/admin content (title, question/choice text, username) rendered through Django auto-escaping; no `|safe`, no `mark_safe`.
- No answer disclosure: quiz GET template emits only choice `id`/`text`, never `is_correct` — correct answers aren't shipped to the client.
- Presigned `src` in `<iframe>`/`<video>` is this user's short-lived URL; no unsigned/public media path. Login `next` redirect validated by Django's host allow-list (no open redirect).

Carry-forward (unchanged): SEC-002 (`.gitignore` before `git init`), SEC-003 (HSTS/SSL-redirect → T5.1), SEC-004 (MinIO root creds → scope service account, T5.1).

Gate verdict: PASS to Phase 4. No blocking vulnerability. SEC-006 mitigated by the planned Cloudflare Access.

## Phase 4 gate — 2026-07-24

Scope: T4.1 `JoinerProgress` CSV export admin action (`core/admin.py`).

SEC-007: CSV formula (spreadsheet) injection
Verdict: ✅ Fixed & verified
Action Needed: none — resolved. Exported cells (name, email, material title) could begin with `= + - @` (or a leading control char) and be executed as formulas when opened in Excel/Sheets. Added `_csv_safe()` which prefixes a single quote to such cells; applied to every field before `writerow`. Verified via inline asserts (`=1+2`→`'=1+2`, `@cmd`→`'@cmd`, benign values unchanged). Export stays admin-only (`is_staff`), no new auth surface.

Gate verdict: PASS to Phase 5. SEC-007 fixed. Carry-forward SEC-002/003/004 → Phase 5 hardening (T5.1).

## Final gate — 2026-07-24

Scope: whole codebase pre-deploy (all lists). Security items below.

SEC-002: no `.gitignore` — `.env` holds secrets
Verdict: 🚫 Open — fix before `git init`
Action Needed: repo is not yet git-initialized; the moment it is, `.env` (real POSTGRES/MINIO/SECRET_KEY) would be committable. Add `.gitignore` covering `.env`, `__pycache__/`, `*.pyc`, `staticfiles/` before any `git init`/commit.

SEC-003: HSTS / SSL redirect
Verdict: ✅ Resolved (T5.1) — `if not DEBUG:` SECURE_SSL_REDIRECT + HSTS 1yr/subdomains/preload. `check --deploy` clean (only W009 placeholder key).

SEC-004: app uses MinIO root credentials
Verdict: ⚠️ Accepted for MVP — documented (README prod notes)
Action Needed: pre-real-deploy, create a bucket-scoped MinIO service account and swap `MINIO_ROOT_*` in app/ensure_bucket for it. Not a code blocker.

SEC-006: no login throttle — Verdict: ⚠️ Accepted — mitigated by Cloudflare Access (P14, README). Unchanged.
SEC-007: CSV formula injection — Verdict: ✅ Fixed (Phase 4). Unchanged.

SEC-OK (verified good): `@login_required` on all joiner views; admin gated by `is_staff`; CSRF on every form incl. logout/quiz; presigned private media (unsigned 403); no `|safe`/`mark_safe`; quiz never ships `is_correct`; compose secrets via `.env` with `:?` guards; nginx never exposes MinIO.

Gate: SEC-002 is the one open security action (cheap). SEC-004/006 accepted+documented.

### Final-gate fixes applied — 2026-07-24
- SEC-002 ✅ Fixed — `.gitignore` added (`.env`, `__pycache__/`, `*.pyc`, `web/staticfiles/`).

## Phase 2 re-audit (post CODE-001 nginx change) — 2026-07-24

Scope: presign / expiry / private bucket, after nginx `/media` was templated from `MINIO_BUCKET` (envsubst).

SEC-008: nginx envsubst could blank the presign-signing `Host` header
Verdict: ✅ Fixed
Action Needed: none — resolved. Presign verifies because nginx forwards `Host $host`; the image's envsubst substitutes *all* env vars, so a future container env var named `host` would blank `$host` and silently break every signature. Pinned `NGINX_ENVSUBST_FILTER=MINIO_BUCKET` so only the bucket segment is templated; runtime vars stay intact.

SEC-OK (verified good, unchanged):
- `MinioMediaStorage.url()` presigns via public-endpoint client, 900s expiry; bucket segment rewritten `/<bucket>/`→`/media/` and nginx rewrites `/media/`→`/${MINIO_BUCKET}/` — both now derive from the same `MINIO_BUCKET`, no drift (CODE-001).
- Private bucket (`AWS_DEFAULT_ACL=None`); unsigned GET 403, signed 200 (verified prior).
- `parameters` into `generate_presigned_url` are internal (name only), not attacker-controlled; no key traversal escapes the bucket namespace.

Carry-forward: SEC-004 (MinIO root creds → service account, Phase 5), SEC-005 (15-min bearer URL, accepted).

Gate verdict: PASS. SEC-008 fixed; no new blocker.
