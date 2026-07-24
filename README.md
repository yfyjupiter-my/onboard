# Onboard

Employee onboarding: HR/IT publish materials (PDF/video) + optional quizzes in Django admin; joiners work through a checklist, view each material, and pass its quiz to complete. Files live in MinIO and reach the browser only via short-lived (15-min) presigned URLs — never public, never through Django.

**Stack:** nginx → Django/gunicorn → Postgres 16 + MinIO, four Docker Compose services on one host.

## Configure

```bash
cp .env.example .env
```

Then edit `.env` and set **real** values (Compose refuses to start without the passwords):

| Var | What |
|---|---|
| `POSTGRES_PASSWORD` | Postgres password |
| `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` | MinIO credentials |
| `DJANGO_SECRET_KEY` | long random string — `python -c "import secrets;print(secrets.token_urlsafe(64))"` |
| `DJANGO_DEBUG` | `False` in production (default) |
| `DJANGO_ALLOWED_HOSTS` | comma-separated hostnames you serve on |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | comma-separated `scheme://host` origins |
| `MINIO_PUBLIC_ENDPOINT` | public base URL the browser hits (presigned GETs are signed against this) |

## Run

```bash
docker compose up --build          # whole stack → http://localhost
```

The `web` container auto-runs `migrate` + `collectstatic` on start, then gunicorn on `:8000`; `ensure_bucket` creates the private MinIO bucket idempotently.

First admin (HR/IT):

```bash
docker compose run --rm web python manage.py createsuperuser
```

Log in at `/admin/` to add Materials, Quizzes, Questions/Choices. Joiners are ordinary users (`is_staff=False`); create them in admin. Export progress from the **Joiner progress** list → *Export selected as CSV*.

## Production notes

- `DJANGO_DEBUG=False` turns on HSTS, SSL redirect, and secure cookies (TLS terminates at nginx/Cloudflare; the proxy `X-Forwarded-Proto` header lets Django see https). Verify with `docker compose run --rm web python manage.py check --deploy` — a real `DJANGO_SECRET_KEY` clears the last warning.
- **Put Cloudflare Access (or equivalent SSO) in front of `/admin/`** — there is no app-level login throttle (SEC-006); Access provides authentication + brute-force protection.
- MinIO currently uses root credentials; scope a bucket-only service account before real deployment (SEC-004).

## Dev commands

```bash
docker compose run --rm web python manage.py makemigrations   # after model changes
docker compose run --rm web python manage.py test core        # test suite
docker compose run --rm web python manage.py test core.tests.QuizFlowTests   # single case
```

> Note: code is baked into the image at build — rebuild (`docker compose build web`) after changing Python files before running tests.
