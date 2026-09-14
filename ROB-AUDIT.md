# ROB-AUDIT — Robustness & Error Handling

## QA check — isolated admin/frontend sessions (T6.6) — 2026-09-14

ROB-001: every anonymous visit to a login page now writes a `django_session` row, and nothing ever deletes old rows
Verdict: ⚠️ Pending
Action Needed: `CSRF_USE_SESSIONS=True` (T6.6) keeps the CSRF token in a DB session, so a cookieless GET of `/login/` or `/admin/login/` creates a row. Measured: 6 GETs → +6 rows. Nothing runs `clearsessions` (18 expired rows already present), so bots or health checks grow the table without limit.
- [ ] ROB-001a **Recommended:** remove `CSRF_USE_SESSIONS` (one line). Session isolation doesn't depend on it. The only cost: logging into one portal rotates the CSRF cookie, so a form already open in the other portal returns 403 once and works after a reload.
- [ ] ROB-001b Either way: run `python manage.py clearsessions` in `entrypoint.sh` + note a daily cron in README (expired sessions pre-date T6.6).

ROB-OK (verified good):
- `/admin` → 301 `/admin/` (APPEND_SLASH); unknown `/admin/...` → admin login redirect; no 500s.
- A garbage or expired `admin_sessionid`/`sessionid` cookie just gets a fresh anonymous session (Django's SessionStore).
- Save, delete, 5xx-skip and `SessionInterrupted` still run through Django's own `process_response`; the subclass only renames the cookie.
- The frontend cookie is stripped from `/admin/` requests, so a leftover pre-T6.6 `sessionid` can't cause errors or authenticate admin.

Gate: **PASS**, no blocker. One pending item (ROB-001).
