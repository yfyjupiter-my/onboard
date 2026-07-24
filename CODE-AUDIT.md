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
