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

## QA check — T6.7 top bar (option B) — 2026-09-15

RUN-006: `topbar_progress` adds 2 COUNT queries to every joiner page
Verdict: ✅ Correct
Action Needed: none. Measured on `/` and `/material/<id>/`: 7 queries total, of which 2 are the COUNTs, taking 1–2 ms combined. The progress COUNT uses the `core_joinerprogress_user_id` index (plus the unique `(user_id, material_id)` constraint), and the materials table is small. Staff and anonymous requests (all of `/admin/`, login) return `{}` before any query.

RUN-007: the scroll handler runs on every scroll event
Verdict: ✅ Correct
Action Needed: none. It is a passive `@scroll.window` that only reads `scrollY` and flips one boolean. Alpine's `:class` effect depends on `hide`, not `y`, so the DOM updates only on a direction change. No layout reads, no forced reflow.

RUN-008: `body{overflow-x:clip}` is ignored before Safari 16
Verdict: ✅ Correct (accepted, informational)
Action Needed: none. The full-bleed bar uses `calc(50% - 50vw)`. On pre-2022 desktop Safari with classic scrollbars, the page could scroll sideways by the scrollbar width (~15px). Mobile Safari has no scrollbar width, so it's unaffected. Chromium verified at 320/390/1280: `scrollWidth` equals the viewport.

RUN-OK: animations are transform/opacity only (the rail uses `scaleX`, the bar uses `translateY`), with no width/height animation. No new static assets or JS files (Alpine was already loaded).

Gate: **PASS**, nothing pending.

## QA check — top bar always pinned (hide-on-scroll removed) — 2026-09-15

RUN-009: cost of scrolling with the sticky bar
Verdict: ✅ Correct
Action Needed: none. Checklist at 1280×800, 240 scroll frames driven by `requestAnimationFrame`: **LayoutCount +0**, LayoutDuration 0ms, frame p50 16.7ms / p95 17.6ms / max 21.5ms (60fps). There are **no `scroll` listeners on `window`** now (CDP `getEventListeners`). The bar has no `transform` or `will-change`, so no extra compositor layer. Chromium handles sticky positioning off the main thread.

RUN-007: superseded. The Alpine `@scroll.window` handler was removed, so there's no per-scroll JS left.

Gate: **PASS**, nothing pending.

## QA check — T6.9 ribbon burst — 2026-09-15

RUN-OK (verified live, Chromium 390px, CPU throttled 6×, first 3.5s after load): 204 frames, median and p95 frame both 16.7ms, 0 frames over 50ms. One 50ms long task during page load, not during the animation. CLS 0 (ribbons are absolutely positioned). 24 elements animate transform/opacity only, which stays on the compositor. The `.fx` container is removed after 3.5s (0 left). Two one-shot timers, no listeners, nothing retained. An incomplete joiner renders 0 ribbons and pays no cost.

Gate: **PASS**, no open items from T6.9.

## QA check — T6.10 link-material loading dots — 2026-09-15

RUN-008: the loading dots' cost while loading and after
Verdict: ✅ Correct
Action Needed: none. There are 3 CSS animations using transform/opacity only (no layout or paint of neighbours). Once the frame loads, `x-show` sets `display:none` and the `mc-bob` animation count drops from 3 to 0 (verified live), so nothing keeps running. CLS 0.0000–0.0002; the 34×20px hint box doesn't move the button. There are no new JS or asset files (inline SVG, about 20 lines of CSS).

Gate: **PASS**, nothing pending.
