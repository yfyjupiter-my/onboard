# RUN-AUDIT — Runtime & Performance Leaks

## QA check — ROB-001/BUS-013 fixes + serving path — 2026-09-14

RUN-001: gunicorn runs its defaults (1 sync worker, 30s timeout)
Verdict: ✅ Correct (fixed)
Action Needed: the compose command passes no `--workers`, and the logs show a single "Booting worker". One slow request blocks every joiner and the healthcheck (5s timeout × 5 retries → marked unhealthy). Slow requests here: an admin upload of up to 512 MB (nginx `client_max_body_size`) or a large CSV export. Measured: a 500 MB upload to MinIO took 2.8s on this host (8 CPUs), but slower disk or network could cross the 30s timeout and kill the upload.
- [x] RUN-001a add `--workers 3 --timeout 120` to the gunicorn line in `docker-compose.yml`.

RUN-002: `clearsessions` adds startup time
Verdict: ✅ Correct
Action Needed: none. It measured 1.47s, mostly Django boot. The delete uses the index on `expire_date`. Start to "Listening" took ~6s, well inside `start_period: 30s` plus the healthcheck retries.

RUN-OK (verified good):
- No more session writes on anonymous visits: 6 GETs → +0 rows (ROB-001 fix holds).
- `SplitSessionMiddleware` costs one small dict copy on `/admin/` requests only; the frontend path is unchanged.
- The probe object used for the upload timing (`qa-probe/probe.bin`) was deleted afterwards, confirmed with `exists` → False.

Fix (2026-09-14): `--workers 3 --timeout 120` added to the gunicorn line in `docker-compose.yml`. Verified: the logs show 3 "Booting worker" lines, `web` is healthy, `/login/` and `/admin/login/` return 200, and 9 concurrent requests finished in 0.08s. Ceiling: 3 sync workers means 3 slow uploads at once still queue joiners. Raise `--workers` (≈ 2×CPU+1) if HR uploads in bulk.

Gate: **PASS**, no blocker, nothing pending.

## QA check — gunicorn 3 workers / 120s timeout (RUN-001 fix) — 2026-09-14

RUN-003: gunicorn never receives SIGTERM, so every stop or redeploy hard-kills in-flight requests
Verdict: ✅ Correct (fixed)
Action Needed: the compose command is `sh -c "migrate && … && gunicorn …"`. Because the chain has no `exec`, `sh` stays PID 1 and gunicorn is only its child. PID 1 `sh` ignores SIGTERM, so Docker waits 10s and then SIGKILLs everything. Measured: `docker compose restart web` took 11s, and the logs had no "Handling signal" / graceful-shutdown line. An admin upload in progress during a redeploy is cut off.
- [x] RUN-003a prefix the last command with `exec`: `exec gunicorn onboard.wsgi:application …` (one word).

RUN-004: a persistent DB connection goes stale after a Postgres restart, so each worker serves one 500
Verdict: ✅ Correct (fixed)
Action Needed: `conn_max_age=600` without health checks. Reproduced: `docker compose restart db`, then 9 DB-touching requests gave `500 500 500 200…` (one per worker, `psycopg.OperationalError: terminating connection`). This scales with `--workers`.
- [x] RUN-004a add `conn_health_checks=True` to `dj_database_url.config(...)` in `settings.py` (dj-database-url 2.3.0 supports it; Django pings the connection once per request before reusing it).

RUN-005: the nginx proxy timeout (60s default) is shorter than the gunicorn timeout (120s)
Verdict: ✅ Correct (fixed)
Action Needed: `location /` has no `proxy_read_timeout`, so nginx returns 504 at 60s while gunicorn keeps working up to 120s. The RUN-001 headroom only exists on paper: an admin upload whose Django→MinIO step passes 60s shows the admin an error even though the file may still save.
- [x] RUN-005a add `proxy_read_timeout 120s;` to `location /` in `nginx/default.conf.template` (matches `--timeout 120`).

RUN-OK (verified good):
- Memory: master 28 MB + 3 workers ~55 MB RSS each (`web` container 137 MiB of 7.6 GiB). Fine.
- DB connections: at most 1 persistent connection per sync worker (3) vs Postgres `max_connections=100`.
- Uploads over 2.5 MB spool to a temp file, not RAM (Django default), and boto3 streams them to MinIO in chunks, so a 512 MB upload doesn't multiply memory per worker.

Fix (2026-09-14), all verified live:
- RUN-003: `exec gunicorn …`. PID 1 is now gunicorn. `restart web` dropped from 11s to 1s, and the logs show `Handling signal: term` → `Shutting down: Master`.
- RUN-004: `conn_health_checks=True`. After `docker compose restart db`, 9 DB-touching requests all returned 200 (before: `500 500 500 200…`).
- RUN-005: `proxy_read_timeout 120s` in `location /`. `nginx -T` shows it loaded. Note: nginx renders templates only at start, so it needs `docker compose restart nginx`.
- `manage.py test core` 32/32.

Gate: **PASS**, no blocker, nothing pending.
