# STATUS

## Done
- `prd.md`, `docker-compose.yml`, `.env.example` present.
- `wireframe.html` — 3 medium-fidelity grayscale layout sets (login, checklist, material viewer, quiz).
- `themes.html` — 3 styling themes on Set B (Corporate Trust / Warm Welcome / Calm Slate dark).
- `DESIGN.md` — reverse-extracted **Warm Welcome** theme (tokens, CSS, components, prohibitions).

## Blocked
- `docker compose up` fails until `web/` (Django) + `nginx/` are scaffolded.

- `mockup.html` — production-ready Set B mockup (login, checklist, material viewer, quiz, result) in Warm Welcome theme.

- `finalize.md` — 15 resolved PRD decisions (P1–P15): django-storages+boto3, presign via `/media` proxy, no per-user assignment (lazy JoinerProgress), quiz pass_mark 80 / unlimited retakes, whitenoise, vendored htmx/Alpine, Python 3.12 / Django 5.x. None block scaffold.

- `TASKS.md` — 6 phases (P0 scaffold → P5 hardening) mapped from finalize.md P1–P15, each with acceptance criteria + audit gate.

- **Phase 0 scaffold ✅** — `web/` Django project (Django 5.2.4, py3.12), `core/` app, env-driven `settings.py` (whitenoise, security keys), `entrypoint.sh` (ensure_bucket→migrate→collectstatic→gunicorn), `nginx/default.conf` (/media→minio, /→web), vendored htmx/Alpine + hand-written `app.css` from DESIGN.md (offline, no Tailwind build). Verified via `docker compose up --build`: web healthy, home/admin/static all 200, `onboard-media` bucket created. nginx blocked only by host :80 already in use (env, not code).

- **Phase 0 audit gate ✅ PASS** — Security (`SEC-AUDIT.md`) + Code Quality (`CODE-AUDIT.md`). No blockers. Pending notes: SEC-001 nginx `/media` presign path/host mismatch (fix in Phase 2/T2.2), SEC-002 add `.gitignore` for `.env` before `git init`, SEC-003 HSTS/SSL-redirect deferred to T5.1; CODE-001 nginx bucket name hardcoded vs `MINIO_BUCKET`, CODE-002 `ensure_bucket` swallows non-404 `ClientError`.

- **Phase 1 ✅** — `core/models.py`: Material, Quiz (1:1, pass_mark 80), Question/Choice (single-correct MVP), JoinerProgress (unique user+material, nullable score/passed/timestamps). Admin: Material+Quiz/Question/Choice inlines CRUD; JoinerProgress read-only. `0001_initial` migration committed; fresh DB migrates clean, `check` 0 issues. Note: migration file root-owned on host (no sudo).

- **Phase 1 audit gate ✅ PASS** — Code Quality (`CODE-AUDIT.md`) + Business Logic (`BUS-AUDIT.md`). No blockers. Pending (Phase 3/T3.4): BUS-001 single-correct-choice invariant unenforced (guard at scoring + admin clean); BUS-002 `pass_mark` can exceed 100 → unpassable (add `MaxValueValidator(100)`).

- **Phase 2 ✅** — `core/storage.py` `MinioMediaStorage` (django-storages 1.14 `S3Storage`): uploads via `minio:9000`, browser GETs presigned against `MINIO_PUBLIC_ENDPOINT` (900s) then bucket segment rewritten to `/media/`; nginx rewrites `/media/`→`/onboard-media/` + forwards `Host` so signatures verify. Private bucket. Settings wired (path-style, private ACL, no-overwrite). New env `MINIO_PUBLIC_ENDPOINT` (default `http://localhost`). Verified in-container: upload OK, unsigned 403, signed 200. **Resolved SEC-001 (presign path/host mismatch), CODE-002 (ensure_bucket narrow except); CODE-001 addressed via nginx comment (fixed single bucket).**

- **Phase 2 audit gate ✅ PASS** — Security (`SEC-AUDIT.md`). SEC-001 resolved & verified (unsigned 403 / signed 200 / 900s). New: SEC-004 app uses MinIO **root** creds → scope to a bucket-only service account in Phase 5 (pending); SEC-005 presigned URLs are 15-min bearer tokens (acceptable for onboarding files). Carry-forward SEC-002 (.gitignore), SEC-003 (HSTS→T5.1). No blocker.

- **Phase 3 ✅** — joiner flow in `core/views.py` (checklist, material_view, quiz) + templates (login, checklist, material, quiz, result, `_topbar`). Django built-in Login/Logout (logout POST), `@login_required` on all joiner views. Checklist left-joins progress (no lazy create); material_view `get_or_create` + state machine (no-quiz→completed, quiz+not_started→viewed), presigned `<iframe>`/`<video>` src; quiz scores `round(correct/total*100)` from prefetched choices, pass_mark gate, unlimited retakes, empty-quiz guard. Result screen plain POST form (htmx skipped). Deleted orphan `home.html`. Verified via test client: login gate, completion state machine, fail 50%/pass 100%, retake, joiner no admin.

- **Phase 3 audit gate ✅ PASS** — Business Logic (`BUS-AUDIT.md`) + Security (`SEC-AUDIT.md`). No blocker. New: **BUS-003** failed retake after completion leaves `status=completed` but `passed=False` → **fix before T4.1** (CSV reads these); BUS-004 quiz-pass-without-view is acceptable (matches P5); SEC-006 no login throttle (mitigated by planned Cloudflare Access). Still pending: BUS-001 (single-correct choice), BUS-002 (pass_mark>100). Verified-good: authz/`@login_required`, no IDOR, CSRF on all forms, auto-escaping, correct answers not shipped to client.

- **BUS-003 fixed** — `quiz()` now guards the overwrite: a failing retake on an already-`completed` material is a no-op, keeping the passing `score`/`passed`/`completed_at`. Exports are consistent.

- **Phase 4 ✅** — T4.1 `JoinerProgress` admin action "Export selected as CSV": stdlib `csv` → `HttpResponse(text/csv)`, `select_related(user, material)` (no N+1). Columns: joiner name (full name or username), email, material title, status, score, passed, completed_at (ISO); None→empty cell. `check` 0 issues.

- **Phase 4 audit gate ✅ PASS** — Compliance/Accessibility (`COM-AUDIT.md`) + CSV-injection (Security). COM-001 PII export is admin-only/data-minimized (acceptable); COM-002 a11y N/A (no new UI). **SEC-007 CSV formula injection fixed** — `_csv_safe()` quotes cells starting `= + - @`/control chars, applied to all fields; verified by inline asserts. No blocker.

- **Phase 5 ✅** — T5.1 prod-only security block (`if not DEBUG`): SECURE_SSL_REDIRECT + HSTS 1yr/subdomains/preload (rest was already wired) → **resolves SEC-003**; `check --deploy` clean except W009 (placeholder SECRET_KEY = operator value). T5.2 `README.md` (config table, run, createsuperuser, CSV export, Cloudflare Access + SEC-004 prod notes, dev/test cmds). T5.3 `core/tests.py` 7 tests (csv_safe, quiz scoring + BUS-003 state machine, no-quiz completion, presign shape) — all green. No volume mount → rebuild image before tests.

- **Final audit gate — ⚠️ 4 open actions (none crash/RCE-class)**. Verified-good: authz/CSRF/presign/no-XSS, quiz scoring + BUS-003, prefetch/select_related (no N+1), HSTS/SSL (SEC-003 resolved), a11y basics. Open: **SEC-002** add `.gitignore` before git init; **COM-003** base.html loads Google Fonts CDN (privacy/GDPR + breaks offline claim); **BUS-001** single-correct-choice unenforced (0-correct = unpassable trap); **BUS-002** pass_mark>100 unpassable (MaxValueValidator). Accepted/deferred: SEC-004 (MinIO service account, README-noted), SEC-006 (login throttle → Cloudflare Access). CODE/RUN/ROB: clean, no action. `check --deploy` clean except W009 (placeholder SECRET_KEY = operator value).

- **Final-gate fixes ✅ (all 4 applied & tested)** — SEC-002 `.gitignore` added; COM-003 Google Fonts CDN removed, Inter+Fraunces vendored locally under `static/fonts/` (offline restored, no IP leak); BUS-002 `pass_mark` `MaxValueValidator(100)` + migration `0002`; BUS-001 `ChoiceInlineFormSet` enforces exactly-one-correct. `manage.py test core` **11/11**; `check --deploy` clean except W009 (placeholder key); no external URLs in templates/css; fonts collected+hashed. No open audit blockers remain.

- **CODE-AUDIT cleanup ✅** — CODE-001 nginx bucket drift resolved: `nginx/default.conf` → `default.conf.template` mounted at `/etc/nginx/templates/`, image envsubst substitutes `${MINIO_BUCKET}` at startup; compose passes `MINIO_BUCKET` to nginx. Storage `url()` rewrite and nginx rewrite now both derive from one env var (no drift). CODE-002 confirmed already fixed (`ensure_bucket` re-raises non-404). Both marked ✅ in `CODE-AUDIT.md`.

- **Phase 2 security re-audit ✅ PASS** (post CODE-001) — presign/expiry/private-bucket surface sound. **SEC-008 fixed** — pinned `NGINX_ENVSUBST_FILTER=MINIO_BUCKET` so envsubst can't blank the presign-signing `Host $host` header. Carry-forward unchanged: SEC-004 (MinIO root creds → service account, Phase 5), SEC-005 (15-min bearer URLs, accepted). Recorded in `SEC-AUDIT.md`.

- **Checklist card content ✅** — cards now reflect the uploaded material: cover shows a `PDF`/`▶` glyph with type-specific gradient (`type-{{material.type}}`), kicker appends `· Quiz` when a quiz is attached. `checklist()` view computes `quiz_material_ids` (one query) and passes `has_quiz` per row.

- **Explicit "Mark complete" button ✅** — no-quiz materials no longer auto-complete on view; viewing marks `viewed` ("In progress") and the joiner clicks **Mark complete** on the material detail page (bottom-right, alongside where the quiz button sits) to finish. New `mark_complete` view (POST-only, `@login_required`, CSRF) + `material/<pk>/complete/` URL; 404s for quiz materials so the pass_mark gate can't be bypassed. Button rendered as a sibling `<form>` (can't nest in the tile `<a>`), shown only on non-completed no-quiz cards. Quiz flow unchanged. `NoQuizViewTests` updated (view→viewed, button→completed, quiz→404); `manage.py test core` **13/13**.

- **Video/PDF playback fix ✅** — after host port moved 90→8080, presigned media URLs 404'd (signed against `http://localhost`:80, browser on :8080) → `<video>` "no supported format". Fixed: `.env` `MINIO_PUBLIC_ENDPOINT=http://localhost:8080`; nginx `/media/` now forwards `Host $http_host` (keeps port) not `$host` (strips it) so MinIO signature verifies. Verified 206 `video/mp4` range response end-to-end. **If host port changes again, update `MINIO_PUBLIC_ENDPOINT` to match.**

- **Review-gated "Mark complete" ✅** — button greyed/disabled until the joiner reviews the material. Alpine `x-data="{reviewed}"`; `:disabled="!reviewed"`; CSS `.btn:disabled`. **Video**: enables on native `@ended`. **PDF**: native iframe can't expose scroll (cross-origin), so PDFs now render via **vendored PDF.js** (`static/vendor/pdf.min.mjs` + `pdf.worker.min.mjs`, offline) page-by-page into a scroll container; Alpine `@scroll` unlocks at the last page (short/1-page PDFs unlock immediately via a synthetic scroll event). Non-PDF/corrupt files (or images/`.md` mis-typed as `pdf`) `.catch` → fall back to native `<iframe>` and unlock (can't scroll-gate). `.mjs` served as `text/javascript` by whitenoise. UX gate only — `mark_complete` view unchanged. Browser-verified: 3-page PDF gates then unlocks on scroll; PNG-as-pdf falls back + unlocks. `material.html`, `app.css`, `static/vendor/pdf*.mjs`.

## Next
- **Deploy prerequisites (operator, not code):** set real `.env` secrets (clears W009), `git init` (`.gitignore` ready), scope MinIO service account (SEC-004), put Cloudflare Access on `/admin/` (SEC-006/P14). App code is deploy-ready.

