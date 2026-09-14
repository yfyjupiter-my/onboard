# ROB-AUDIT — Robustness & Error Handling

## QA check — isolated admin/frontend sessions (T6.6) — 2026-09-14

ROB-001: every anonymous visit to a login page now writes a `django_session` row, and nothing ever deletes old rows
Verdict: ✅ Correct (fixed)
Action Needed: `CSRF_USE_SESSIONS=True` (T6.6) keeps the CSRF token in a DB session, so a cookieless GET of `/login/` or `/admin/login/` creates a row. Measured: 6 GETs → +6 rows. Nothing runs `clearsessions` (18 expired rows already present), so bots or health checks grow the table without limit.
- [x] ROB-001a **Recommended:** remove `CSRF_USE_SESSIONS` (one line). Session isolation doesn't depend on it. The only cost: logging into one portal rotates the CSRF cookie, so a form already open in the other portal returns 403 once and works after a reload.
- [x] ROB-001b Either way: run `python manage.py clearsessions` in `entrypoint.sh` + note a daily cron in README (expired sessions pre-date T6.6).

ROB-OK (verified good):
- `/admin` → 301 `/admin/` (APPEND_SLASH); unknown `/admin/...` → admin login redirect; no 500s.
- A garbage or expired `admin_sessionid`/`sessionid` cookie just gets a fresh anonymous session (Django's SessionStore).
- Save, delete, 5xx-skip and `SessionInterrupted` still run through Django's own `process_response`; the subclass only renames the cookie.
- The frontend cookie is stripped from `/admin/` requests, so a leftover pre-T6.6 `sessionid` can't cause errors or authenticate admin.

Fix (2026-09-14): removed `CSRF_USE_SESSIONS`, back to the CSRF cookie. The healthcheck on `/admin/login/` every 10s alone was writing ~8,640 rows/day. `clearsessions` now runs after `migrate` in the compose `web` command, plus a daily cron in README (Production step 8). Verified live: 18 expired rows → 0; 6 anonymous GETs → +0 rows. Test `test_admin_login_page_creates_no_session_row`.

Gate: **PASS**, no blocker, nothing pending.

## QA check — ROB-001/BUS-013 fixes (clearsessions on start, cookie CSRF, hidden View site) — 2026-09-14

ROB-002: `clearsessions` sits in the `web` startup `&&` chain, so if it fails gunicorn never starts
Verdict: ✅ Correct
Action Needed: none. It's a single indexed `DELETE FROM django_session WHERE expire_date < now()` (checked with query capture). It can only fail if the DB is unreachable, and then `migrate` just before it fails first. `restart: unless-stopped` retries. `docker compose run --rm web …` overrides the command, so tests and one-off commands don't run it.

ROB-003: the daily cron runs `docker compose exec -T web …` while `web` is down
Verdict: ✅ Correct
Action Needed: none. The cron run fails harmlessly and the next `web` start purges anyway. Expired sessions are already rejected at read time, so the purge only reclaims space.

ROB-OK (verified good):
- Cookie CSRF is back. A form left open in the other portal after a login returns 403 once and works after a reload, with no 500 (documented in T6.6).
- `web` restarted clean: healthy, `restarts=0`, no errors in the logs.
- Hiding "View site" (`site_url=None`) only drops the header link; admin pages render normally (test-verified).

Gate: **PASS**, no blocker, nothing pending.
