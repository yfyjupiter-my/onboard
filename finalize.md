# finalize.md — Resolved PRD Open Questions

Every decision `prd.md` left as "either is fine" or underspecified, pinned to one concrete choice so implementation can start. One default per item; deviate only if the user overrides.

---

P1: Django ↔ MinIO client — `django-storages` vs raw `boto3`
Status: ✅ Resolved
Action Needed: Use **`django-storages[s3]` + `boto3`** as `DEFAULT_FILE_STORAGE`. Admin `FileField` uploads land in MinIO automatically (no custom upload code); presigned GETs come from the same boto3 client via `storage.url(key)`. One dependency, covers both upload and presign.

---

P2: Presigned URL host — must match the public Cloudflare domain
Status: ✅ Resolved
Action Needed: boto3 client `endpoint_url=http://minio:9000` for **uploads** (container-to-container). For **browser GETs**, generate the presign against `AWS_S3_CUSTOM_DOMAIN=<domain>/media` so the signed URL is `https://<domain>/media/<key>?X-Amz-...`; nginx reverse-proxies `/media/` → `minio:9000`. Expiry **900s (15 min)**. MinIO never directly exposed. `ponytail:` two endpoints is the minimum that makes signatures verify behind the proxy.

---

P3: Material → joiner assignment (data model gap — no assignment table in PRD)
Status: ✅ Resolved
Action Needed: **No per-user assignment for MVP.** Every active `Material` applies to every joiner (`is_staff=False`). `JoinerProgress` rows are created **lazily** on first view of a material (`get_or_create`). Checklist = all active materials left-joined to this user's progress. Per-department assignment is explicitly v2.0 (Non-Goals) — do not build an assignment model now.

---

P4: Quiz shape, pass threshold, retakes
Status: ✅ Resolved
Action Needed:
- `Quiz`: 1:1 optional on `Material`, field `pass_mark` (int %, default **80**).
- `Question`: FK→Quiz, `text`, `order`. `Choice`: FK→Question, `text`, `is_correct` (bool). Supports MC and T/F (T/F = two choices). Single correct choice per question for MVP.
- Scoring: `score = round(correct/total*100)`; `passed = score >= pass_mark`.
- **Retakes: unlimited, no cooldown.** Each submit overwrites `JoinerProgress` score/passed/submitted_at. (Timed/cooldown retakes = post-MVP per Risks.)

---

P5: "Viewed" vs "completed" state machine
Status: ✅ Resolved
Action Needed: `JoinerProgress.status ∈ {not_started, viewed, completed}`.
- GET `/material/<id>/` → `get_or_create` progress, set `viewed` if `not_started`.
- Material **without** quiz → set `completed` + `completed_at` on that same view.
- Material **with** quiz → `completed` only when a submit yields `passed=True`.
Fields: `status`, `score` (nullable), `passed` (nullable bool), `submitted_at`, `completed_at`.

---

P6: Material types
Status: ✅ Resolved
Action Needed: `Material.type` choices = **`pdf`, `video`** (MVP). Viewer renders `<iframe>`/`<embed>` for pdf, `<video controls>` for video, `src` = presigned URL. Image/other deferred — add a choice when a real need appears (YAGNI).

---

P7: Frontend asset delivery (no node runtime in prod)
Status: ✅ Resolved
Action Needed: **CDN-less is not required** but a node build is out of scope. Vendor pinned static files into `web/static/`:
- **Tailwind** via the standalone **Tailwind CLI** at build time → one `output.css` committed/collected (no node in the running container). `ponytail:` if the CLI step is friction, fall back to the Play CDN `<script>` for MVP and note it.
- **htmx** + **Alpine.js**: vendored minified JS in `web/static/vendor/`, served by whitenoise/nginx. No CDN dependency at runtime (works behind the tunnel offline).

---

P8: Static file serving in the container
Status: ✅ Resolved
Action Needed: **whitenoise** middleware serves Django static (`collectstatic` in entrypoint). nginx handles only `/media/*` (MinIO proxy) + pass-through to gunicorn. Avoids a separate static-files nginx location config.

---

P9: htmx + Django CSRF
Status: ✅ Resolved
Action Needed: Add `hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'` on `<body>` (or the htmx-enabled form). Keep `{% csrf_token %}` in real `<form>`s. No custom middleware.

---

P10: Superuser / first admin bootstrap
Status: ✅ Resolved
Action Needed: **Manual**, per CLAUDE.md: `docker compose run --rm web python manage.py createsuperuser`. No auto-seed of credentials in code/env (avoids a baked-in default password). Document in README.

---

P11: MinIO bucket creation
Status: ✅ Resolved
Action Needed: Single bucket **`onboard-media`**, name from `.env` (`MINIO_BUCKET`). Create it idempotently in the `web` entrypoint (boto3 `head_bucket`/`create_bucket`) before gunicorn — no manual `mc` step (matches AC "no manual mc cp").

---

P12: Django settings split & env loading
Status: ✅ Resolved
Action Needed: Single `settings.py` reading `os.environ` (Compose injects `.env`). No dev/prod split module for MVP — toggle via `DJANGO_DEBUG`. Required security keys wired: `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO','https')`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`. `ponytail:` one settings file until a second environment actually exists.

---

P13: CSV export
Status: ✅ Resolved
Action Needed: Django admin action **"Export selected as CSV"** on `JoinerProgress` admin, stdlib `csv` module → `HttpResponse(content_type=text/csv)`. Columns: joiner name, email, material title, status, score, passed, completed_at. No extra dependency.

---

P14: Cloudflare Access on `/admin/`
Status: ⚠️ Deferred (not blocking)
Action Needed: **Out of code scope** — it's a Cloudflare dashboard/tunnel config, not Django. Document as a recommended deploy step in README. Django-side admin stays protected by `is_staff` + session auth. No code change needed to add Access later.

---

P15: Versions
Status: ✅ Resolved
Action Needed: **Python 3.12**, **Django 5.x (LTS-track)**, **postgres:16** (per compose), **minio** latest stable, **gunicorn**. Pin exact versions in `requirements.txt` / Dockerfile at scaffold time.

---

## Blocking check
None of the above block scaffolding. Phase 0 (scaffold) can proceed on these defaults. The only human-gated step is P10 (createsuperuser) and P14 (Cloudflare Access), both post-scaffold deploy actions, not code.
