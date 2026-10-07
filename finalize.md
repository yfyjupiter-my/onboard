# finalize.md — Resolved PRD Open Questions

Every decision `prd.md` left as "either is fine" or underspecified, pinned to one concrete choice so implementation can start. One default per item; deviate only if the user overrides.

---

## Decisions

Standing decisions made **after** P1–P15 below, during implementation. The audit files hold the full reasoning and the alternatives that lost; this table is the index, so a decision isn't re-litigated from scratch. P1–P15 remain the scaffold-time decisions.

| # | Decision | Why | Recorded in |
|---|---|---|---|
| D1 | Media reaches the browser **only** via 15-min presigned URLs signed for the public host; bucket stays private, bytes never pass through Django | one code path for upload and read, no public bucket to misconfigure, no gunicorn worker tied up streaming an MP4 | P2 below, `SEC-001` |
| D2 | App signs with MinIO **root** credentials — scoped service account deferred | works, and the creds never leave the Compose network; scoping is a deploy step, not code | `SEC-004` (⚠️ accepted), README prod step 5 |
| D3 | **No app-level login throttle** — Cloudflare Access in front of `/admin/` supplies it | an in-app throttle is a lockout/storage problem of its own for an internal tool behind SSO | `SEC-006` (⚠️ accepted), P14 below |
| D4 | Admin and joiner site use **separate session cookies**; `/admin/` is staff-only, joiner site rejects staff | an HR session must not silently become a joiner session (and vice versa); the cost is two accounts for one person | `SEC-016`, README "two accounts, two doors" |
| D5 | `DJANGO_HTTPS` is its **own** env switch (default `True`), not derived from `not DEBUG` | a plain-http LAN pilot needs `DEBUG=False` *and* non-Secure cookies; tying them together forced one of the two to be wrong | `SEC-035`, README Step 2 |
| D6 | Joiner admin page is **view-only** (`has_change_permission=False`, readonly fields) | it rendered the full `User` form, so `change_joiner` alone could grant superuser; joiners are edited in Users admin by a superuser | `SEC-028`, `SEC-029` |
| D7 | Joiners list/CSV **allowlists** URL filters (`is_active` only) | `?password__startswith=` turned the changelist into a hash oracle; an allowlist can't be outgrown by new model fields | `SEC-030`, `SEC-033/034` |
| D8 | Completion gates (PDF last page, video `ended`) are **client-side UX only**; the server only requires the material was opened | real proof needs per-page/per-second server acks — out of MVP scope; the gate is a nudge, not an access control | `BUS-006` (⚠️ accepted) |
| D9 | A PDF or video that **won't render unlocks** Mark complete instead of staying disabled | a mislabeled upload otherwise strands a joiner with no way to finish onboarding; failing open is the lesser harm given D8 | `BUS-006`, `BUS-007` |
| D10 | Lock rule lives in **one** function, `Material.locked_ids(materials, done)` | gate, checklist and the admin joiner page had drifted copies of it; three truths about "is this locked" is a bug factory | `BUS-029` |
| D11 | A chapter whose materials are **all** locked opens immediately; HR must keep ≥1 unlocked material in any chapter using locks | locked materials never block each other, so there's no deadlock to code around; the rule is in the field's help text | `BUS-011` (accepted, option a) |
| D12 | Switching a material's type **drops a now-invalid stored file** (and its MinIO object), but a *new* wrong upload is an error | the dead end was being unable to save at all; silently discarding what the user just picked is the worse of the two | `BUS-022` (option a) |
| D13 | `Material.type` extended past P6 to **pdf, video, link, image**; `chapter` + `locked` added | real content didn't fit two types; chapters are a fixed list, not a model (`ponytail:` promote if HR needs to rename them) | `web/core/models.py`, T6.x in `TASKS.md` |
| D14 | Video **captions are burned into the MP4** — no separate track/`<track>` file | one file to upload and presign; a sidecar caption file means a second object, a second presign and a sync problem | `COM-009`, README Step 5 |
| D15 | `Material.description` is **hidden** in admin; image `alt` falls back to the title | the field had no way to be set and no one was setting it; field + data kept so it can come back | `CODE-011`, `COM-029` (accepted) |
| D16 | `TIME_ZONE=Asia/Kuala_Lumpur` with `USE_TZ=True`; CSV timestamps localized on export | storage stays UTC (portable), humans read +08:00 in admin and in the export | `STATUS.md` T6.18 |
| D17 | Opening a material via **GET** marks it Viewed (cross-site link can do it); not moved to POST | Viewed ≠ completed — completion still needs POST + CSRF token or a passed quiz; progress-on-first-view is P3/P5 | `SEC-043` (accepted) |

Deferred by design, do not build without being asked: per-department material assignment (P3), timed/cooldown retakes (P4), an ADR/RFC process (one contributor — `prd.md` + this table + the audit files cover it).

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
Status: ✅ Resolved (superseded by **D13** — link + image added)
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
