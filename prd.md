# PRD: Onboard — New Joiner Onboarding Platform

## 1. Executive Summary

**Problem Statement**: New joiners currently receive essential onboarding material (employee handbook, security awareness video, policies) via scattered emails/shared drives, with no record of who actually reviewed or completed them.

**Proposed Solution**: A lightweight, self-hosted web platform where new joiners log in, view/download onboarding materials, and complete short quizzes/acknowledgements per material. HR/IT manage users and content through a Django admin-backed UI. All files live in a self-hosted MinIO instance; metadata, users, and completion records live in PostgreSQL. The whole stack (Django, PostgreSQL, MinIO, nginx) runs as Docker containers via Docker Compose on a single on-premise Ubuntu 22.04 server. The platform is **published online under the company's own domain**, exposed through a **Cloudflare Tunnel** — the server keeps zero inbound ports open (stays behind NAT), and Cloudflare terminates public TLS at its edge and proxies traffic down the tunnel.

**Success Criteria**:
- 100% of new joiners have a trackable completion record within their first week.
- Admin can publish a new material (upload file + attach quiz) in under 5 minutes, no code changes.
- Zero material files stored outside MinIO (single source of truth).
- Entire stack runs via `docker compose up` on a single on-premise Ubuntu 22.04 server; the only external dependency is Cloudflare (DNS + tunnel + edge TLS).
- Platform reachable at `https://<company-domain>` from the public internet with a valid Cloudflare cert and no inbound firewall ports opened on the server.
- Quiz pass rate and view status visible per-user in one admin screen.
- Every quiz result is persisted to the database on submit, and the full completion/quiz dataset is one-click exportable as `.csv` from admin.

## 2. User Experience & Functionality

### User Personas
- **New Joiner**: Logs in with their own account, views assigned materials (handbook, security video, etc.), completes quizzes, sees their own progress.
- **HR/IT Admin**: Creates joiner accounts, uploads/organizes materials, attaches quizzes, monitors completion status across all joiners.

### User Stories
- As a **new joiner**, I receive a username/password created by HR/IT and log in at a single login page — I never self-register — so access is controlled and tied to my real identity.
- As a **new joiner**, I want to log in and see a checklist of my onboarding materials, so I know what's left to complete.
- As an **HR/IT admin**, I create a joiner's login credentials in the Django admin portal and hand them to the joiner out-of-band (e.g. email/onboarding pack), so only provisioned hires can reach the platform.
- As a **new joiner**, I want to view a PDF handbook or stream a security video in-browser, so I don't need to download separate apps.
- As a **new joiner**, I want to take a short quiz after a material, so I can confirm I understood it and mark it done.
- As an **admin**, I want to upload a new material (file + optional quiz) through Django admin, so IT doesn't need to touch the server manually.
- As an **admin**, I want to create/deactivate joiner accounts, so access is only given to current new hires.
- As an **admin**, I want to see a per-joiner and per-material completion dashboard, so I can confirm onboarding is finished before probation review.
- As an **admin**, I want to export all completion + quiz results to a `.csv` file from the admin, so I can hand HR a compliance record or open it in Excel.

### Acceptance Criteria
- Joiner cannot mark a material "complete" without passing its quiz (if one is attached); materials with no quiz are marked complete on view.
- Every quiz submission is **persisted to PostgreSQL** on submit (score, pass/fail, submitted_at) — the completion record survives logout, container restart, and is the single source of truth, never client-side only.
- Admin can **export completion + quiz records as `.csv`** directly from Django admin (a "Export selected as CSV" action on the progress list), containing at minimum: joiner name, email, material title, status, quiz score, pass/fail, completed_at. Uses the Python stdlib `csv` module — no extra dependency.
- Video/PDF materials stream directly from MinIO via signed/temporary URLs — never public buckets, never routed through Django as a file passthrough for large files where avoidable.
- Admin sees, per joiner: list of assigned materials, view status (not started/viewed/completed), quiz score, completion date.
- **Login gateway**: a single login page is the only entry point — every non-public URL requires an authenticated session and redirects unauthenticated visitors to login. No self-signup, no password self-reset for MVP (HR/IT resets in admin).
- Joiner credentials are **created exclusively in the Django admin portal by HR/IT** and delivered to the joiner out-of-band; the joiner logs in with those credentials, is landed on their own checklist, and can see only their own materials/progress.
- Deactivated joiner accounts immediately lose login access.
- All uploads (PDF, MP4, etc.) go through Django admin file upload, which pushes to MinIO — no manual `mc cp` or console steps required for day-to-day content publishing.

### Non-Goals
- No public/anonymous access — every viewer is an authenticated account.
- No SSO/LDAP/AD integration for MVP — local Django accounts only.
- No multi-tenant / multi-company support.
- No mobile app — responsive web only.
- No content authoring tools (video editing, PDF generation) — admin uploads finished files only.
- No analytics beyond completion tracking (no heatmaps, time-on-page, etc.).
- No automated email/reminder system for MVP (may revisit in v1.1).

## 3. AI System Requirements

Not applicable — this platform has no AI/LLM component. (Quizzes are static, admin-authored multiple-choice/true-false, not AI-generated or AI-graded.)

## 4. Technical Specifications

### Tech Stack
- **Backend/Admin**: Django (Python), using Django's built-in admin for content and user management.
- **Frontend**: Django server-rendered templates + **htmx** (no-reload quiz submit / progress updates via HTML fragments) + **Tailwind CSS** for styling + **Alpine.js** for small client-side flourishes. No SPA, no separate API layer, no node runtime in production. HR/IT UI is Django admin (not rebuilt).
- **Database**: PostgreSQL — users, materials metadata, quizzes, questions, completion records.
- **Object Storage**: MinIO (self-hosted, S3-compatible) — actual file bytes (PDFs, videos, images).
- **Deployment**: Docker Compose on a single on-premise Ubuntu 22.04 server, published online via Cloudflare Tunnel under the company's own domain.
- **Edge/Ingress**: Cloudflare — authoritative DNS for the domain, edge TLS termination, and a `cloudflared` tunnel (fifth container) that dials out to Cloudflare so no inbound ports are exposed.
- **Auth**: Django's built-in auth (session-based), local accounts only, admin-created (no self-signup). Login gateway uses Django's stock `LoginView`/`login_required` (or `LoginRequiredMiddleware`) — no custom auth code, no third-party auth library.

### Architecture Overview
```
[Public Browser] --HTTPS--> [Cloudflare edge (DNS + TLS)]
                                     | (outbound tunnel, no open ports)
                             [cloudflared container]
                                     v
                             [nginx container] --> [django (gunicorn)] --SQL--> [postgres]
                                     |                     |
                                     |                     +--S3 API (boto3, presigned URLs)--> [minio]
                                     +--/media/* reverse-proxy (presigned GETs)------------------> [minio]
```
- Five Docker Compose services: `cloudflared`, `nginx`, `web` (Django/gunicorn), `db` (postgres), `minio`. All on one Compose network, one `docker-compose.yml`.
- `cloudflared` holds a tunnel credential/token (from `.env`) and forwards Cloudflare traffic to `nginx:80` internally — the server opens **no** inbound ports (80/443 not published to the host).
- MinIO presigned URLs are generated with the **public domain** (e.g. `https://<domain>/media/...`) and reverse-proxied by nginx to the `minio` service, so the browser reaches files over the same Cloudflare-fronted hostname — MinIO itself is never directly exposed.
- `db` and `minio` use named Docker volumes for persistence (`pgdata`, `minio-data`) — survives container recreation, lives on the host's Ubuntu filesystem.
- Django app serves pages, handles auth/session, and quiz logic.
- File uploads from admin go through Django → boto3 → MinIO bucket (container-to-container on the Compose network, not committed to git, not on host disk directly).
- File downloads/streams use MinIO presigned URLs (time-limited) so the browser fetches directly from the MinIO container (via nginx reverse proxy), keeping Django out of the large-file data path.
- Data model (core tables): `User`, `Material` (title, type, MinIO object key, description), `Quiz` (1:1 or none with Material), `Question`, `Choice`, `JoinerProgress` (user, material, status, quiz score, `passed`, `submitted_at`, `completed_at`) — this table is the persisted quiz-result / completion record and the source for CSV export.
- Config (DB credentials, MinIO keys, Django secret key) passed via `.env` file consumed by Compose — never baked into images.

### Integration Points
- **Django ↔ PostgreSQL**: standard Django ORM, migrations via `manage.py migrate` (run as a one-off Compose command or entrypoint step on container start).
- **Django ↔ MinIO**: `django-storages` with S3 backend pointed at the `minio` service's container name (e.g. `http://minio:9000`) on the Compose network, or direct `boto3` client — either is fine given single-server scope.
- **Auth / login gateway**: Django admin site (`/admin/`) reused for staff/HR; a single joiner-facing login page (`/login/`) for non-staff users is the sole gateway to the joiner app. Credentials for joiners are provisioned only via Django admin (User create) by HR/IT — there is no registration endpoint. All joiner views are `login_required`; unauthenticated hits redirect to `/login/`.

### URL Routes

Server-rendered Django views — **no JSON/REST API layer**. All routes are session-authenticated (Django cookie); htmx POSTs hit ordinary view URLs that return HTML fragments, not JSON.

| Route | Method | Access | Purpose |
|---|---|---|---|
| `/login/` | GET, POST | Public | Login gateway (Django `LoginView`); sole entry point |
| `/logout/` | POST | Auth | End session, redirect to `/login/` |
| `/` | GET | Joiner | Onboarding checklist / dashboard (their own materials + progress) |
| `/material/<id>/` | GET | Joiner | Material viewer (PDF/video via presigned MinIO URL); marks viewed |
| `/material/<id>/quiz/` | GET, POST | Joiner | Take quiz; POST submits answers → HTML fragment with result, persists `JoinerProgress` |
| `/admin/` | GET, POST | HR/IT (`is_staff`) | Django admin: users, materials, quizzes, completion dashboard, CSV export action |
| `/media/*` | GET | Auth | nginx reverse-proxy to MinIO for presigned object GETs |

- All joiner routes are `login_required`; unauthenticated hits redirect to `/login/`. Joiners only ever see their own `JoinerProgress` (queryset filtered by `request.user`).
- No registration/self-signup route exists by design — accounts are created only in `/admin/`.

### Security & Privacy
- Public traffic served over HTTPS with a valid Cloudflare edge certificate (no self-signed cert; no browser warnings). Cloudflare fronts the domain, giving DDoS protection, WAF, and TLS by default.
- Server opens **zero inbound ports** — all ingress arrives via the outbound-only `cloudflared` tunnel, so the on-prem box is not directly reachable from the internet (no port-forwarding, no exposed public IP).
- `web` (Django) must set `DJANGO_ALLOWED_HOSTS` to the real domain, `CSRF_TRUSTED_ORIGINS=https://<domain>`, `SECURE_PROXY_SSL_HEADER` (trust Cloudflare/tunnel `X-Forwarded-Proto`), and secure/HTTPS-only session + CSRF cookies. Consider Cloudflare Access in front of `/admin/` to gate HR/IT staff.
- MinIO buckets private by default; access only via presigned URLs with short expiry (e.g. 15 min), scoped to the public `/media/` path so MinIO stays behind nginx.
- Passwords hashed via Django's default (PBKDF2); no plaintext storage.
- Joiner accounts scoped to `is_staff=False`; only HR/IT get `is_staff=True` for Django admin access.
- Regular `pg_dump` (from the `db` container) + backup of the `minio-data` Docker volume, both to attached storage on the same host — single point of failure accepted for MVP given small internal scope, documented as a known risk.
- No PII beyond name/email/role is stored; no payment or highly sensitive data in scope.

## 5. Risks & Roadmap

### Phased Rollout
- **MVP**: Django admin content/user management, joiner login, view materials, quiz + completion tracking (results persisted to PostgreSQL), CSV export of completion/quiz records from admin, admin completion dashboard. Deployed on single Ubuntu server with PostgreSQL + MinIO.
- **v1.1**: Email/reminder notifications for incomplete onboarding; bulk joiner import (CSV); basic search across materials.
- **v2.0**: SSO/LDAP integration if company scales beyond local accounts; scheduled/emailed reports and richer export formats; per-department material assignment.

### Technical Risks
- **Cloudflare dependency**: DNS, edge TLS, and tunnel now sit on the ingress path — a Cloudflare outage or misconfigured tunnel token takes the platform offline. Accepted for MVP (standard, well-run dependency); tunnel token must be stored in `.env` only, never committed.
- **Single server = single point of failure**: no HA for MVP given "lightweight/local" scope — mitigate with scheduled backups (Postgres + MinIO), documented and accepted risk, not solved in MVP.
- **Large video files**: streaming large MP4s directly from MinIO via presigned URL avoids overloading Django/gunicorn, but disk space on the single server is a hard constraint — monitor MinIO volume usage.
- **No SSO for MVP**: acceptable at current small scale (<100 users/year); revisit if headcount growth makes manual account creation a bottleneck.
- **Quiz logic simplicity**: MVP quizzes are static MC/TF only — if compliance requirements demand more complex assessment (timed, randomized, retakes-with-cooldown), scope should be revisited before v1.1.
