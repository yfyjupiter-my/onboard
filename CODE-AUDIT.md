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

---

## T6.11 Image material type: code quality check (2026-09-15)

CODE-007: image format lookup duplicated; stale "PDF/video" comments
Verdict: ✅ Correct (fixed)
Action Needed: `clean()` and `source_url` each rebuilt the extension lookup. Moved it to one `Material.image_format` property. Updated the comments in `models.py`, `views.py` (ROB-005) and `admin.py` (remove-file) that still said "PDF/video". Tests 39/39.

CODE-008: migration and tests
Verdict: ✅ Correct
Action Needed: None. `0008_material_type_image` only changes choices (no SQL). `max_length=5` fits `"image"`. One test covers the extension/header allowlist and the forced content type.

---

## T6.12: code quality check (2026-09-15)

CODE-009: one source of truth for extensions
Verdict: ✅ Correct
Action Needed: None. `FILE_EXTENSIONS[IMAGE] = tuple(IMAGE_FORMATS)`, so the image allowlist and served content types can't drift. `clean()` does one extension check for every file type, then the magic-byte check for new image uploads only. Migrations 0009 (AddField) and 0010 (help text) are additive.

CODE-010: ROB-012 assertions were inside the image-upload test
Verdict: ✅ Correct (fixed)
Action Needed: moved to their own `test_file_extension_must_match_type`, so a failure names the rule that broke. Tests 41/41, `check` 0 issues.

## T6.15 hide "Image description" in admin: code quality check (2026-09-15)

CODE-011: `Material.description` has no way to be set
Verdict: ⚠️ Pending (user decision)
Action Needed: The column, its help text (mentions a field HR no longer sees), the template `default:` fallback and `test_image_alt_uses_description_else_title` remain. Nothing breaks. Options: (a) keep it, so the row can come back with a one-line change (recommended); (b) remove the field with migration `0012` and simplify alt to the title (no data lost today, 0 rows).

CODE-012: exclude placement and page render
Verdict: ✅ Correct
Action Needed: None. The add and change pages return 200 without the row, and the `url`/file widgets are unaffected. `check` passes; `core` tests OK.
