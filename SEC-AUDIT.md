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

## Post-Phase-5 audit — review gate + compose changes — 2026-07-27

Scope: published MinIO console port, vendored PDF.js, `material.html` fallback iframe, `mark_complete` endpoint.

SEC-009: MinIO **console** published on host `:9001` with root credentials
Verdict: 🚫 Blocking for deploy (LAN/prod), ⚠️ acceptable on a dev laptop
Action Needed: `docker-compose.yml` maps `9001:9001` on all interfaces, so the console login is reachable from the whole LAN (and any port-forward), guarded only by `MINIO_ROOT_USER/PASSWORD` — the same unrotated root creds as SEC-004. Compromise = every material plus the ability to rewrite them. Fix: bind loopback only (`127.0.0.1:9001:9001`) or drop the mapping and use `docker compose exec minio mc` / an SSH tunnel when the console is needed. Combine with SEC-004 (bucket-scoped service account for the app).

SEC-010: PDF fallback renders an uploaded file **same-origin** in an unsandboxed iframe
Verdict: ⚠️ Open — staff→joiner stored XSS path
Action Needed: `/media/` is proxied on the app's own origin, so when PDF.js fails the fallback `<iframe src="{{ file_url }}">` executes whatever the file is. An HTML/SVG uploaded through the admin (staff-only, so not a joiner-reachable escalation) then runs script in the app origin — same-origin iframe can read the parent DOM, the session-bound CSRF token, and act as the viewing joiner. Two cheap fixes, apply both:
- `frame.sandbox = ''` on the fallback iframe (no `allow-scripts`; native PDF viewing still works).
- `add_header X-Content-Type-Options nosniff always;` in the nginx `/media/` location so the browser honours MinIO's stored Content-Type instead of sniffing HTML.

SEC-011: vendored PDF.js provenance unrecorded
Verdict: ✅ Correct — no action beyond a note
Action Needed: `static/vendor/pdf.min.mjs` / `pdf.worker.min.mjs` are pdf.js **4.6.82** (Mozilla, Apache-2.0), i.e. after the CVE-2024-4367 font-handler RCE fixed in 4.2.67 — not vulnerable. No version or checksum is written down anywhere. Record "pdf.js 4.6.82" in `README.md` alongside htmx/Alpine so future upgrades are auditable.

SEC-OK (verified good):
- `mark_complete` — `@login_required` + `@require_POST` + CSRF token; scoped to `request.user`; 404s on quiz materials; no IDOR.
- `JoinerLoginForm` blocks `is_staff` on the joiner login route (admin surface separated).
- `{{ file_url|escapejs }}` / `{{ material.title|escapejs }}` correctly escaped inside the JS module; no `|safe`, no `mark_safe`.
- PDF.js is a same-origin module + worker (no CDN); no external URLs in templates/CSS.
- Presign/private-bucket surface unchanged since the Phase 2 re-audit; nginx still never exposes `:9000`.

Carry-forward unchanged: SEC-004 (root creds → service account), SEC-005 (15-min bearer URLs, accepted), SEC-006 (login throttle → Cloudflare Access).

Gate verdict: **FAIL for LAN/prod deploy on SEC-009** (one-line compose fix), SEC-010 open (two one-line fixes). No RCE/crash-class issue in app code.

### Fixes applied — 2026-07-27
- SEC-009 ✅ Fixed — MinIO console bound to `127.0.0.1:9001:9001` (verified: `docker compose port minio 9001` → `127.0.0.1:9001`). README notes the SSH-tunnel workflow.
- SEC-010 ✅ Fixed — fallback iframe gets `frame.sandbox = ''` (no `allow-scripts`) **and** nginx `/media/` sends `X-Content-Type-Options: nosniff always`. `nginx -t` passes.
- SEC-011 ✅ Recorded — pdf.js 4.6.82 (+ htmx/Alpine) listed in `README.md` production notes.

## QA check — admin joiner export (T6.2 / T6.3) — 2026-07-28

Scope: `c2335de` + `da914f6` — `Joiner` proxy admin, three CSV export paths (bulk action, changelist-wide `core_joiner_export`, per-joiner `core_joiner_export_one`), the two custom `get_urls` endpoints, and the joinerprogress→joiner redirect. Joiner flow, storage/presign and auth were untouched and are not re-audited here.

SEC-012: CSV export checks `view_joiner` but never `view_joinerprogress`
Verdict: ⚠️ Open — low (staff-only, no joiner-reachable path)
Action Needed: `export_one_view`/`export_all_view` gate on `has_view_permission` for the **Joiner** model only, then `_csv()` reads `JoinerProgress` rows unconditionally. Verified: a staff account holding just `core.view_joiner` downloads every joiner's email, per-material status, score and pass flag. Nothing in the deployment grants that split today (HR is superuser), so this is a latent least-privilege gap, not a live leak. Fix: in `_csv()` (single choke point, all three callers) `if not request.user.has_perm("core.view_joinerprogress"): raise PermissionDenied` — needs `request` threaded through, ~3 lines. Same-file note: `export_one_view` runs `get_object_or_404` **before** the permission check, so an unprivileged staff user distinguishes "joiner exists" (403) from "doesn't" (404); swap the two lines while you're in there.

SEC-013: unhandled `IncorrectLookupParameters` on the changelist-wide export → HTTP 500
Verdict: ⚠️ Open — robustness, not a disclosure
Action Needed: `export_all_view` calls `get_changelist_instance(request)` directly; Django's own `changelist_view` wraps that call in `try/except IncorrectLookupParameters` and redirects to `?e=1`. Here it propagates. Verified: `GET /admin/core/joiner/export-csv/?is_active__exact=bogus` → **500**. `DEBUG=False` means no traceback reaches the browser, so the impact is a broken export link (any stale/hand-edited filter querystring) plus 500s in the log, not information disclosure. Fix: wrap the call, `except IncorrectLookupParameters: return redirect("admin:core_joiner_changelist")`.

SEC-014: arbitrary local-field lookups reach the export queryset (`?password__startswith=…`)
Verdict: ✅ Accepted — inherited Django behaviour, no privilege gain
Action Needed: none required. The export reuses the ChangeList queryset, and `ModelAdmin.lookup_allowed()` returns True for any single-part local field, so `?password__startswith=pbkdf2` filters the export. Verified as a working presence oracle (`pbkdf2` → 1 row, `zzzz` → 0), i.e. a staff user can walk a joiner's password **hash** character by character. This is identical to what Django already permits on `/admin/auth/user/?password__startswith=…` for anyone with changelist access, so the export adds no new capability — the boundary is "who is staff", which P14/SEC-006 puts behind Cloudflare Access. Close it properly by overriding `lookup_allowed` on `JoinerAdmin` to an allowlist (`is_active`, `username`, `email`, plus the search fields) if the staff set ever widens beyond HR/IT.

SEC-OK (verified good):
- Both new endpoints wrapped in `admin_site.admin_view` — anonymous and joiner sessions get 302 → `/admin/login/`; staff without model perms get **403** on both (verified).
- `export_one_view` resolves the pk against `get_queryset()` (which filters `is_staff=False`), so a staff/superuser pk **404s** — no staff PII leaks through the joiner export (verified).
- `_csv_safe()` still applied to every cell on all three export paths (SEC-007 holds); `Content-Disposition` filename is a constant, not interpolated.
- Exports are read-only GETs with no state change; a forced cross-origin request can't be read back, so the missing CSRF token is correct, not an omission.
- `{{ request.GET.urlencode }}` in `change_list.html` is auto-escaped; no `|safe` in either new template.
- `admin.site.get_app_list` monkeypatch is display-ordering only — it re-calls the original, so per-app permission filtering is unchanged.
- `0004_joiner` is proxy-only; the `joinerprogress` → joiner 301 is a static `pattern_name` redirect with no user input in the target.

Gate verdict: **PASS** — no blocker, no joiner-reachable issue. Two one-liners open (SEC-012, SEC-013), one accepted (SEC-014). Carry-forward unchanged: SEC-004, SEC-005, SEC-006.

### Fixes applied — 2026-07-28
- SEC-012 ✅ Fixed — `_require_export_perm(request)` requires **both** `view_joiner` and `core.view_joinerprogress`; called from `_csv()` (the choke point all three export paths reach) and again at the top of `export_one_view` **before** `get_object_or_404`, so the 403-vs-404 existence oracle is closed. Verified: `view_joiner`-only staff → 403 on all three paths and 403 for a non-existent pk; both perms → 200; staff pk still 404.
- SEC-013 ✅ Fixed — `export_all_view` wraps `get_changelist_instance` in `try/except IncorrectLookupParameters` → 302 to the joiner changelist. Verified: `?is_active__exact=bogus` → **302 /admin/core/joiner/** (was 500).
- SEC-014 — unchanged, accepted as inherited Django behaviour. Revisit with a `lookup_allowed` allowlist if staff access widens past HR/IT.
- Regression cover: `core/tests.py` gains `test_export_needs_progress_permission` + `test_export_survives_a_bad_filter_value`. `manage.py test core` **27/27**. `check --deploy` (DEBUG=False) clean except W009 (placeholder SECRET_KEY = operator value).
