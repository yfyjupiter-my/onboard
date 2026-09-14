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
