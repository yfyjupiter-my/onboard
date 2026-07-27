# Onboard

Employee onboarding: HR/IT publish materials (PDF/video) + optional quizzes in Django admin; joiners work through a checklist, review each material, and either click **Mark complete** or pass its quiz. Files live in MinIO and reach the browser only via short-lived (15-min) presigned URLs — never public, never streamed through Django.

**Stack:** nginx (`:8080`) → Django 5.2 / gunicorn (`:8000`) → Postgres 16 + MinIO. Four Docker Compose services on one host.

---

## ⚠️ Read this first — the two things that break every setup

1. **Pick ONE address for the whole deployment and use it everywhere.**
   Media URLs are cryptographically signed for exactly one host, so `MINIO_PUBLIC_ENDPOINT`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` and the URL you type in the browser must all agree — **including the port**.
   - Single machine only → `http://localhost:8080`
   - Other devices on the LAN → `http://<server-LAN-IP>:8080` (then even the server itself must browse that IP, *not* `localhost`)
   - Real deployment → `https://onboard.example.com`

   `MINIO_PUBLIC_ENDPOINT` is a **single URL**, never a comma-list. Only `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS` take commas.

2. **Two accounts, two doors.** `/admin/` accepts **staff only**; the joiner site **rejects staff**. An HR/IT person who also needs to take onboarding needs two accounts. Never set `is_staff=True` on a joiner — it locks them out of the joiner login.

---

## Prerequisites

- Linux host (tested on Ubuntu 24.04) with **Docker Engine + the Compose v2 plugin** (`docker compose version` must work).
- Free host ports: **8080** (the app) and **127.0.0.1:9001** (MinIO console, loopback only).
- ~2 GB RAM, plus disk for uploaded PDFs/videos.
- No Python/Node needed on the host — everything runs in containers.

---

## Step 1 — Get the code

```bash
git clone <your-repo-url> onboard
cd onboard
```

`.env` is gitignored; nothing secret ships in the repo.

## Step 2 — Create `.env`

```bash
cp .env.example .env
```

Generate a real secret key:

```bash
python3 -c "import secrets;print(secrets.token_urlsafe(64))"
```

Then edit `.env`. Compose **refuses to start** if the password vars are missing.

| Var | Required | What to set |
|---|---|---|
| `POSTGRES_DB` / `POSTGRES_USER` | no | defaults `onboard` / `onboard` |
| `POSTGRES_PASSWORD` | **yes** | any strong password (only reachable inside the Compose network) |
| `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` | **yes** | MinIO credentials; password ≥ 8 chars |
| `MINIO_BUCKET` | no | default `onboard-media`; created automatically on first boot |
| `MINIO_PUBLIC_ENDPOINT` | **yes** | the single browser-facing base URL — see the warning above |
| `DJANGO_SECRET_KEY` | **yes** | the generated random string |
| `DJANGO_DEBUG` | **yes** | `False` in production (see the http/LAN caveat below) |
| `DJANGO_ALLOWED_HOSTS` | **yes** | comma-separated hostnames/IPs you serve on, e.g. `localhost,127.0.0.1,192.168.100.210` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | **yes** | comma-separated `scheme://host:port` origins, exactly as typed in the browser |

Example for a LAN pilot on `192.168.100.210`:

```dotenv
MINIO_PUBLIC_ENDPOINT=http://192.168.100.210:8080
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=192.168.100.210,localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=http://192.168.100.210:8080
```

> **Why `DEBUG=True` for a plain-http LAN pilot:** with `DEBUG=False` Django marks the session and CSRF cookies `Secure`, so the browser never sends them over `http://` and every login fails CSRF. Either keep `DEBUG=True` on the LAN, or put real TLS in front — do not run `DEBUG=True` on the internet.

## Step 3 — Start the stack

```bash
docker compose up --build -d
docker compose ps          # all four services should be healthy
```

On startup the `web` container runs `ensure_bucket` (creates the private MinIO bucket, idempotent) → `migrate` → `collectstatic` → gunicorn on `:8000`. `db` and `minio` are health-gated, so `web` waits for them.

Open your chosen URL, e.g. `http://localhost:8080/` — it redirects to the login page.

Watch logs if anything looks wrong:

```bash
docker compose logs -f web
```

## Step 4 — Create the first HR/IT admin

```bash
docker compose run --rm web python manage.py createsuperuser
```

Log in at `/admin/`.

## Step 5 — Add content

In `/admin/`:

1. **Materials** — title, type (`pdf` or `video`), and the file itself (uploaded straight into MinIO; nginx allows up to 512 MB).
2. **Quiz** (optional, 0 or 1 per material) — `pass_mark` defaults to 80, max 100.
3. **Questions / Choices** — edited inline under the quiz. Each question must have **exactly one** correct choice; the admin form rejects anything else (a question with zero correct answers would be unpassable).

## Step 6 — Add joiners

Still in `/admin/` → **Users** → add user, leave **staff status unchecked**. Joiners need no per-material assignment: every material appears on every joiner's checklist, and progress rows are created as they go.

## Step 7 — What the joiner does

1. Log in at `/` → checklist of all materials (cards show a PDF/▶ glyph and a `· Quiz` tag when a quiz is attached).
2. Open a material → status becomes *In progress*.
   - **PDF** renders page-by-page via vendored PDF.js; **Mark complete** unlocks once scrolled to the last page.
   - **Video** unlocks **Mark complete** when playback ends (or immediately if the file won't play, so nobody gets stranded).
   - This gate is client-side UX only; the server just requires that the material was actually opened.
3. Material **with** a quiz has no Mark-complete button — it completes only on scoring ≥ `pass_mark`. Retakes are unlimited, and a failed retake never un-completes an already-passed material.

## Step 8 — Export progress

`/admin/` → **Joiner progress** → **tick the rows you want** → action *Export selected as CSV* → Go.
With nothing ticked Django just re-renders the page with "Items must be selected" — that is the usual "the export doesn't work" report. Columns: joiner name, email, material, status, score, passed, completed_at (ISO).

---

## Production deployment

1. **TLS in front.** Terminate https at a reverse proxy / Cloudflare and forward to host `:8080`. nginx already passes `X-Forwarded-Proto`, so Django sees https.
2. **`DJANGO_DEBUG=False`** — turns on SSL redirect, HSTS (1 year, subdomains, preload) and secure cookies. Verify:
   ```bash
   docker compose run --rm web python manage.py check --deploy
   ```
   A real `DJANGO_SECRET_KEY` clears the last warning (W009).
3. **Set `MINIO_PUBLIC_ENDPOINT=https://your-domain`** and put the same origin in `DJANGO_CSRF_TRUSTED_ORIGINS`, the host in `DJANGO_ALLOWED_HOSTS`.
4. **Put Cloudflare Access (or equivalent SSO) in front of `/admin/`** — there is no app-level login throttle (SEC-006); Access supplies authentication and brute-force protection.
5. **Scope MinIO credentials** — the app currently uses MinIO *root* creds (SEC-004). Create a service account limited to the one bucket before real use.
6. **MinIO console** is bound to `127.0.0.1:9001` (SEC-009) — reach it with an SSH tunnel, never publish it:
   ```bash
   ssh -L 9001:127.0.0.1:9001 user@server   # then http://localhost:9001
   ```
7. **Back up both volumes** — `pgdata` (all metadata/progress) and `minio-data` (the files). Database dump:
   ```bash
   docker compose exec db pg_dump -U onboard onboard > backup-$(date +%F).sql
   ```
8. **Vendored frontend libs** (no CDN, offline by design) under `web/static/vendor/`: htmx 1.9.x, Alpine 3.x, **pdf.js 4.6.82** (Apache-2.0; ≥ 4.2.67, past CVE-2024-4367). Fonts (Inter, Fraunces) are self-hosted under `web/static/fonts/`. Re-record versions here on upgrade.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| "CSRF verification failed" on login | The origin you typed isn't in `DJANGO_CSRF_TRUSTED_ORIGINS` (needs exact scheme+host+port). Over plain http with `DEBUG=False`, secure cookies are never sent — set `DEBUG=True` for a LAN pilot or use https. |
| Checklist loads but video/PDF is blank, or "no supported format" | `MINIO_PUBLIC_ENDPOINT` doesn't match the host in the address bar. Set it to the exact URL every device uses, then `docker compose up -d`. |
| `EndpointResolutionError` opening a material | `MINIO_PUBLIC_ENDPOINT` contains a comma-list. It is a single URL. |
| Changed the host port from 8080 | Update `MINIO_PUBLIC_ENDPOINT` (and CSRF origins) to the new port — presigns include it. |
| `DisallowedHost` | Add the hostname/IP to `DJANGO_ALLOWED_HOSTS`. |
| Admin login rejects a joiner account | `/admin/` is staff-only; the joiner site is non-staff-only. Use the right account. |
| `docker compose up` exits with "set POSTGRES_PASSWORD in .env" | `.env` missing or the required vars still blank. |
| Code changes don't take effect | Code is baked into the image at build — `docker compose build web && docker compose up -d`. |

---

## Dev commands

```bash
docker compose run --rm web python manage.py makemigrations        # after model changes
docker compose run --rm web python manage.py test core             # full suite (16 tests)
docker compose run --rm web python manage.py test core.tests.QuizFlowTests   # single case
docker compose exec nginx nginx -t                                 # validate proxy config
docker compose down          # stop (volumes kept)
docker compose down -v       # stop AND delete database + uploaded files
```

Migrations run automatically on `web` startup; `makemigrations` is the only step you run by hand.

## Project docs

| File | Purpose |
|---|---|
| `CLAUDE.md` | Doc map and working rules |
| `prd.md` / `finalize.md` | Scope and resolved design decisions |
| `TASKS.md` / `STATUS.md` | Phase breakdown and current snapshot |
| `DESIGN.md` | Visual design system (Warm Welcome theme) |
| `SEC-` / `CODE-` / `BUS-` / `COM-AUDIT.md` | Audit findings and their status |
