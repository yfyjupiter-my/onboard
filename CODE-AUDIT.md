# CODE-AUDIT — Code Quality & Architecture Flaws

## Phase 0 gate — 2026-07-24

Scope: scaffold only. No feature code yet.

CODE-001: bucket name hardcoded in nginx, diverges from `MINIO_BUCKET`
Verdict: ✅ Fixed
Action Needed: Done. `nginx/default.conf` → `default.conf.template`, mounted at `/etc/nginx/templates/` so the nginx image's envsubst substitutes `${MINIO_BUCKET}` at startup. Compose passes `MINIO_BUCKET` to the nginx service. Single source of truth; no drift. (nginx runtime vars like `$host`/`$1` are untouched — envsubst only replaces env-defined names.)

CODE-002: `ensure_bucket` treats every `ClientError` as "bucket missing"
Verdict: ✅ Fixed
Action Needed: Done. `ensure_bucket.py` now re-raises unless `Error.Code in ("404","NoSuchBucket")` before calling `create_bucket`.

CODE-OK: verified-good (no action)
- Settings are env-driven and flat; no premature abstraction. Middleware order correct (whitenoise after security).
- `STORAGES` default `FileSystemStorage` is a documented placeholder ("swapped to S3 in Phase 2") — fine for Phase 0; no `MEDIA_ROOT` needed until uploads exist.
- entrypoint is minimal (`ensure_bucket` → `exec "$@"`); migrate/collectstatic/gunicorn live in compose `command`. Reasonable split.
- Requirements pinned with `==`. Dockerfile slim, no build cruft.
- App layout (`core/` stubs for models/admin/views) matches TASKS phasing; no speculative code.

Gate verdict: PASS to Phase 1. No architectural blocker.

---

## Phase 1 gate — 2026-07-24

Scope: `core/models.py`, `core/admin.py`, `0001_initial` migration.

CODE-003: `related_name="progress"` reused on both JoinerProgress FKs
Verdict: ✅ Correct
Action Needed: None. `user.progress` and `material.progress` live on different models — no reverse-accessor clash. Reads clearly. Left as-is.

CODE-OK: verified-good (no action)
- Models flat, no premature abstraction; choices as class constants, `__str__` on each. Ordering (`Question.order`, `Quiz` verbose_name) sensible.
- Single-correct-choice assumption documented in a comment on `Choice` (per AC).
- Admin: staff-only by Django default (`is_staff`); JoinerProgress correctly read-only (`has_add_permission=False` + all fields `readonly_fields`) — progress is machine-written, not hand-edited.
- Migration is a single clean `0001_initial`; fresh DB migrates, `check` 0 issues.

Gate verdict: PASS to Phase 2 (Code Quality). No architectural blocker.

## QA check — T6.6 session middleware + startup config — 2026-09-14

CODE-004: `ADMIN_PREFIX = "/admin/"` in `core/middleware.py` duplicates `path("admin/", …)` in `onboard/urls.py`
Verdict: ✅ Correct (accepted)
Action Needed: none. The duplication is marked with a comment. If the admin URL is ever moved (for example renamed for hardening), `SessionIsolationTests` fails, because it uses `reverse("admin:login")` and asserts the `admin_sessionid` cookie is set. The drift can't happen silently. Deriving the prefix via lazy `reverse()` inside middleware would add code to guard against something the test already catches.

CODE-005: `SplitSessionMiddleware` design
Verdict: ✅ Correct
Action Needed: none. A 30-line subclass that renames the cookie on the way in and out, with no copy of Django's save/expiry/delete logic, so Django upgrades still apply. Scoped to `/admin/` only; one responsibility. `request.COOKIES` is replaced with a copy, not mutated in place.

CODE-006: startup steps live in two places (`entrypoint.sh`: `ensure_bucket`; compose `command`: migrate → clearsessions → collectstatic → gunicorn)
Verdict: ✅ Correct (accepted)
Action Needed: none for code. README describes the real order. Note for the doc owner: `CLAUDE.md` "Architecture & Commands" still says `web/` and `nginx/` aren't scaffolded and that the entrypoint runs migrate. It's out of date, but I didn't edit it.

CODE-OK (verified good):
- The test helper `_admin_login` keeps admin tests using `force_login` (no password round-trip). New tests assert behaviour (cookies, status codes, session row count), not implementation details.
- No dead code left from the `CSRF_USE_SESSIONS` revert. `makemigrations` isn't affected, since no model changed.

Gate: **PASS**, no blocker, nothing pending.
