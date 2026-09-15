# BUS-AUDIT — Business Logic & State Vulnerabilities

## Phase 1 gate — 2026-07-24

Scope: `core/models.py`, `core/admin.py`. State machine and quiz scoring are Phase 3 runtime; here we only audit what the *schema* lets an admin create that Phase 3 will trust.

BUS-001: single-correct-choice invariant is unenforced at the data layer
Verdict: ⚠️ Pending (address in Phase 3 / T3.4)
Action Needed: Nothing stops an admin saving a `Question` with **zero** or **multiple** `is_correct=True` choices. Phase 3 scoring (`correct/total`) then silently miscounts — a 0-correct question is unpassable, a 2-correct question is ambiguous. Cheapest fix at scoring time: treat "question answered correctly" as `chosen_choice.is_correct` (single-answer radio), and add an admin-side guard (`ChoiceInline` clean / `save` check) that exactly one choice is correct. Do NOT add a DB constraint now (partial-unique across a related table is heavier than the guard). Track for T3.4.

BUS-002: `pass_mark` accepts values > 100 → permanently unpassable quiz
Verdict: ⚠️ Pending (cheap to fix here or T3.4)
Action Needed: `PositiveIntegerField(default=80)` allows e.g. 150. Score maxes at 100, so `score >= pass_mark` never true and the material can never complete. Add `MaxValueValidator(100)` on the field. One line; no migration data risk. Fold into Phase 3 or a follow-up migration.

BUS-OK: verified-good (no action)
- `UniqueConstraint(user, material)` prevents duplicate progress rows — the lazy `get_or_create` in Phase 3 relies on this; correct to enforce at DB level.
- Nullable `score`/`passed`/`submitted_at`/`completed_at` correctly model the not-started/viewed states (no premature defaults implying a taken quiz).
- `on_delete=CASCADE` throughout is right for MVP: deleting a Material tears down its quiz/questions/choices/progress cleanly.

Gate verdict: PASS to Phase 2. No blocker — BUS-001/002 are Phase 3 scoring concerns, not schema blockers, and are tracked.

---

## Phase 3 gate — 2026-07-24

Scope: `core/views.py` (checklist, material_view, quiz), quiz templates. Focus: state machine + scoring integrity.

BUS-003: a failed retake after completion leaves `status=completed` but `passed=False`/low `score`
Verdict: ✅ Fixed (2026-07-24, `core/views.py` `quiz()`)
Action Needed: Resolved. Added guard `if not (progress.status == COMPLETED and not passed):` around the overwrite block — a failing retake on an already-completed material is a no-op (keeps the passing `score`/`passed`/`completed_at`). Passing retakes and normal fail-then-pass paths unchanged. Phase 4 CSV now reads consistent rows.

BUS-004: quiz can be passed without ever opening the material
Verdict: ✅ Acceptable (informational)
Action Needed: none. POST to `/material/<id>/quiz/` `get_or_create`s progress and can go straight to `completed` without a prior GET of the material. This matches P5 ("completed when a submit passes") — passing the quiz is the completion criterion, viewing isn't required. Noted so it isn't mistaken for a bug later.

BUS-OK: verified-good (no action)
- Progress is always scoped to `request.user` (`get_or_create(user=request.user, ...)`) — a joiner can't read or mutate another's progress; no IDOR on state.
- Failed/blank answers handled: missing `q<id>` → `None not in correct_ids` → counts wrong, no crash; `required` radios are UX only, server is authoritative.
- Scoring reads choices from `prefetch_related` (no N+1); empty-quiz guard avoids div-by-zero (`score=0`, can't pass).
- Retake semantics correct for the normal path: fail keeps `viewed` + records attempt; pass sets `completed` + `completed_at`; unlimited, no cooldown.

Carry-forward (still pending, both cheap, target Phase 4/T3.4 follow-up): BUS-001 (single-correct-choice invariant unenforced — now live in scoring), BUS-002 (`pass_mark` > 100 → unpassable).

Gate verdict: PASS to Phase 4. No blocker. BUS-003 fixed (see above); export now reads consistent status/score/passed.

## Final gate — 2026-07-24

BUS-001: single-correct-choice invariant unenforced
Verdict: ⚠️ Open — admin-side data trap
Action Needed: `Choice.is_correct` is free per choice. A question with **0** correct choices is permanently unpassable (joiner stuck); **>1** correct means any marked choice scores. Scoring degrades gracefully (no crash/security issue) but HR can misconfigure silently. Fix: validate "exactly one correct per question" in the ChoiceInline formset (`clean`). Low effort, closes the trap.

BUS-002: `pass_mark` can exceed 100 → unpassable
Verdict: ⚠️ Open — one-line fix
Action Needed: `Quiz.pass_mark` is `PositiveIntegerField(default=80)` with no ceiling; `>100` makes the quiz impossible. Add `validators=[MaxValueValidator(100)]` (+ makemigrations).

BUS-OK (verified good): BUS-003 failing-retake-keeps-pass fixed + tested; quiz scoring `round(correct/total*100)`; empty-quiz guard →0; unique (user, material); no IDOR (submit touches only `request.user`).

Gate: two open items, both cheap, neither a security/crash risk.

### Final-gate fixes applied — 2026-07-24
- BUS-001 ✅ Fixed — `ChoiceInlineFormSet.clean()` enforces exactly one correct choice per question (admin). Tests: valid / zero / two.
- BUS-002 ✅ Fixed — `Quiz.pass_mark` gains `MaxValueValidator(100)` (migration `0002`). Test: 150 → ValidationError.

## Post-Phase-5 audit — "Mark complete" review gate — 2026-07-27

Scope: `mark_complete` view, `material_view` state machine, PDF.js / video review gate (`material.html`), checklist card flags.

BUS-005: `mark_complete` trusts the client — no server-side proof the material was opened
Verdict: ⚠️ Open — completion-record integrity
Action Needed: the view `get_or_create`s progress and sets `completed` regardless of prior status. A joiner with a session + CSRF token can `POST /material/<id>/complete/` for a material they never opened; the record then reads "Completed" in the HR CSV. The `reviewed` gate is Alpine-only (client). Fix (one line): only complete when a progress row already exists with `status=VIEWED` —
`progress = get_object_or_404(JoinerProgress, user=request.user, material=material, status=JoinerProgress.VIEWED)`
Keeps idempotency (already-completed → 404/no-op) and forces a real `material_view` hit first. Does not (and cannot) prove the human read it — that is BUS-006.

BUS-006: PDF review gate unlocks on any PDF.js error
Verdict: ⚠️ Accepted — UX gate only, but bypass is trivial
Action Needed: the `.catch` fallback unlocks the button whenever rendering fails — including transient failures (expired presign, offline tab, blocked worker), not just mislabeled uploads. Anyone wanting to skip can force an error. Acceptable while the gate is cosmetic; if completion must mean "read it", the proof has to be server-side (e.g. POST a per-page ack), which is out of scope for the MVP. Document as a known limit rather than harden the client.

BUS-007: video-type material whose file will not play leaves the joiner permanently stuck
Verdict: ⚠️ Open — joiner-blocking data trap (mirror of BUS-006's PDF fallback)
Action Needed: PDFs fall back and unlock on error; `<video>` has no such path. A material saved as `type=video` with an unplayable/mislabeled file never fires `ended`, so **Mark complete** stays disabled forever and the joiner cannot finish onboarding. Fix (one attribute): `@error="reviewed = true"` on the `<video>` element, matching the PDF fallback.

BUS-OK (verified good):
- `mark_complete` 404s for quiz materials — the pass_mark gate cannot be shortcut.
- No IDOR: progress is always keyed to `request.user`; `is_active=True` filter on every lookup.
- `material_view` no longer auto-completes; NOT_STARTED→VIEWED only, never downgrades COMPLETED.
- BUS-003 guard intact (failing retake keeps the passing record).
- Checklist `quiz_material_ids` is one extra query, no N+1, display-only (no authz decision).

Gate: three open items — BUS-005 and BUS-007 are cheap one-liners, BUS-006 is a documented limit.

### Fixes applied — 2026-07-27
- BUS-005 ✅ Fixed — `mark_complete` now `get_object_or_404`s an existing `JoinerProgress` and only completes from `VIEWED`; never-opened material → 404, already-completed → idempotent redirect. Tests: `test_mark_complete_button_completes` (views first), `test_mark_complete_rejects_unopened_material` (404, no row created).
- BUS-007 ✅ Fixed — `<video @error="reviewed = true">` mirrors the PDF fallback, so an unplayable/mislabeled video can't strand the joiner.
- BUS-006 ⚠️ Accepted, unchanged — client-side gate by design; server-side proof of reading is out of MVP scope.

---

## QA check — T6.4 dashboard chapters — 2026-09-14
Scope: `Material.chapter` + migration `0006`, `checklist()` grouping/counts, `checklist.html` sections, `MaterialAdmin` list.

BUS-008: a material whose `chapter` is not in `CHAPTER_CHOICES` disappears from the joiner dashboard
Verdict: ⚠️ Pending — latent data trap (no bad rows today)
Action Needed: `checklist()` loops over `CHAPTER_CHOICES` and only shows materials matching one of them. `choices` is checked by the admin form but not by the database, so a chapter value that isn't in the list hides the material from joiners while it is still active. That can happen through a shell/ORM write, a data import, or a later edit that removes or renumbers a chapter. HR's joiner admin (T6.2) still counts it in `completed / active materials`, so every joiner looks permanently behind on an item they cannot see. Fix (view only, no migration): build the sections from the chapters the active materials actually have, e.g. `itertools.groupby(materials, key=attrgetter("chapter"))` over the existing `order_by("chapter", "created_at")`, with the name from `dict(CHAPTER_CHOICES).get(n, f"Chapter {n}")`. Every active material then always renders. Add one assert to `ChecklistChapterTests` with a `chapter=9` row.

BUS-OK (verified good):
- Counts match the admin: both use active materials only, and `done` counts `COMPLETED` only, so a quiz item counts only once passed. The BUS-003 guard is unchanged.
- Moving a material to another chapter keeps joiner progress (`JoinerProgress` is keyed by material, not chapter).
- Migration `0006` is an additive `AddField` with `default=1`, so existing rows land in Chapter 1 and no data is rewritten. Verified applied on the live DB.
- No authorization change: progress is still `request.user.progress` and every lookup keeps its `is_active` filter. No new joiner input.
- Hiding empty chapters is display-only. Locking is out of scope by decision, so joiners can take items in any order.
- Still 3 queries on the checklist, grouped in Python (O(chapters × materials), trivial at onboarding scale).

Gate: **PASS**, no blocker. One latent item (BUS-008) with a view-only fix.

### Fixes applied — 2026-09-14
- BUS-008 ✅ Fixed — `checklist()` now groups with `itertools.groupby(materials, attrgetter("chapter"))` over the existing `order_by("chapter", "created_at")`, and the name comes from `dict(CHAPTER_CHOICES).get(n, f"Chapter {n}")`. Every active material always renders; a chapter value that isn't listed shows as "Chapter N" instead of disappearing. `ChecklistChapterTests` asserts that a `chapter=9` material shows up. `manage.py test core` 28/28.

## QA check — locked materials (T6.5) — 2026-09-14

BUS-009: a completed locked material locks again when a new material is added
Verdict: ✅ Fixed — `is_locked_for` and `checklist()` now treat an already-completed material as never locked. The regression assert is in `LockedMaterialTests`.
Action Needed: `Material.is_locked_for()` ignores the joiner's own progress on the locked material. Example: a joiner passes "Final assessment", then HR adds or re-activates any unlocked material. The final assessment locks again, so its tile shows "Locked · complete the other materials first" instead of "Completed". The chapter count still counts it as done (`done / total`), so the tile and the count disagree, and the joiner can't reopen what they already passed. Fix: a material the user has already `COMPLETED` is never locked. Add that check in `is_locked_for` (`JoinerProgress … material=self, status=COMPLETED`) and in `checklist()` (`m.locked and m.id not in completed and not unlocked_all_done`). Then add one assert to `LockedMaterialTests`: complete the locked one, add a new unlocked material, and check it stays open.

BUS-010: a locked URL shows Django's bare "403 Forbidden" page
Verdict: ✅ Fixed — `_open_material` returns None when locked and all 3 endpoints redirect to `home`. The gate still runs before `get_or_create`, and the tests now expect 302.
Action Needed: there's no `403.html`, so a stale tab or bookmark to a locked material shows an unstyled error with no way back. Fix (no new template): in `_open_material`, redirect to `home` instead of raising `PermissionDenied`. The checklist already explains the lock. Keep the check before any `get_or_create`, and update the 3 status assertions in `LockedMaterialTests` from 403 to 302.

BUS-OK (verified good):
- The checklist and the server agree: `unlocked_all_done` (in-memory) and `is_locked_for` (DB) use the same set of active, `locked=False` materials and count `COMPLETED` only. A failed quiz (`VIEWED`) does not unlock anything.
- No deadlock: locked materials never block each other, and with everything locked, `all([])` / `.exists()` both return open.
- Deactivating a material removes it from the requirement on both sides, and inactive materials 404 before the lock check.
- A quiz on a locked material can't be scored: the gate runs before `get_or_create`, so no `JoinerProgress` row is written (asserted in the test).
- Migration `0007` is an additive `AddField(default=False)`, so existing materials stay unlocked. Applied on the live DB.

Gate: **PASS**, no blocker. BUS-009 and BUS-010 fixed, 29/29 tests green.

## QA check — locked materials scoped per chapter (T6.5) — 2026-09-14

BUS-011: a chapter whose materials are all locked opens straight away
Verdict: ✅ Accepted (option a, 2026-09-14) — HR keeps at least one unlocked material in any chapter that uses locks. No code change.
Action Needed: locks now look only at the material's own chapter, and locked materials never block each other. So if a chapter contains only locked materials, for example a "Final assessment" on its own in Chapter 3, it opens immediately and doesn't wait for Chapters 1–2. The admin help text says "in the same chapter", so this is documented. Pick one: (a) accept it and tell HR to keep at least one unlocked material in a chapter that uses locks, or (b) extend the rule so that a chapter with no unlocked materials waits on the earlier chapters. Recommend (a), since it needs no code.

BUS-012: TASKS.md T6.5 still quotes the old label and tile text
Verdict: ✅ Fixed — T6.5 now says "locked until the rest of its chapter is completed" / "Locked · complete the rest of this chapter first" / "all-locked chapter = open".
Action Needed: docs only.

BUS-OK (verified good):
- The checklist and the server agree. `checklist()` checks each `groupby` chapter group, which holds active materials ordered by chapter. `is_locked_for` filters `is_active=True, locked=False, chapter=self.chapter`. Both use the same set and count `COMPLETED` only. The old `unlocked_all_done` from the earlier BUS-OK note is gone.
- An unfinished material in another chapter doesn't block. This is asserted in `LockedMaterialTests` on the checklist and in `is_locked_for`.
- Moving a material to another chapter recomputes its lock against the new chapter on both sides, and progress stays attached to the material. BUS-009 still holds: a completed material is never locked.
- No deadlock: locked materials still never block each other.
- `0007` changed only `verbose_name`/`help_text`, so there's no schema change and `makemigrations --check` reports no changes.

Gate: **PASS**, no blocker. One product decision is open (BUS-011). 29/29 tests.

## QA check — isolated admin/frontend sessions (T6.6) — 2026-09-14

BUS-013: the admin "View site" link leads nowhere useful for staff
Verdict: ✅ Correct (fixed)
Action Needed: `admin.site.site_url` defaults to `/`. For a staff user that's the frontend login page, which rejects staff accounts, so the link is a dead end now that the sessions are split.
- [x] BUS-013a set `admin.site.site_url = None` in `core/admin.py` (hides the link). One line.

BUS-014: a joiner promoted to staff keeps their live frontend session
Verdict: ✅ Correct (accepted)
Action Needed: none. Frontend views don't check `is_staff`, so the promoted account can keep using its existing frontend session until logout. Blocking staff sessions on the frontend was offered for T6.6 and declined. New staff logins at the frontend are still rejected by `JoinerLoginForm`. A staff user demoted to joiner loses admin on the next request (`is_staff` is checked on every request).

BUS-OK (verified good):
- Logging in or out on one portal doesn't affect the other (`SessionIsolationTests`).
- A password change or `is_active=False` still ends sessions on both sides, because the session auth hash and `is_active` are checked on every request whichever cookie is used.
- `/login/?next=/admin/` sends a joiner to the admin login page. There's no bypass.
- The messages cookie is shared (`Path=/`), but the frontend templates never render messages, so admin messages can't leak to the frontend.

Fix (2026-09-14): `admin.site.site_url = None` in `core/admin.py`; test `test_admin_has_no_view_site_link`. 32/32.

Gate: **PASS**, no blocker, nothing pending.

---

## QA check — Business Logic & State (2026-09-14, commit 07a4ace: Joiners admin "last activity" / "completed")

BUS-015: "last activity" is login or completion time, not a live presence status
Verdict: ⚠️ Pending (low)
Action Needed: Sessions last 2 weeks (`SESSION_COOKIE_AGE=1209600`) and `last_login` only changes on a fresh login. A joiner who stays logged in and only *views* materials keeps an old time (viewing has no timestamp). Completing a material or passing a quiz does update it. Choose one:
- [x] BUS-015a rename the column to "last login / completion" so HR doesn't read it as online status. One line. **Recommended.**
- [ ] BUS-015b accept as is. A live "last seen" would need a new field, middleware and a DB write on every request, and a new TASKS item.

BUS-016: joiners with no login and no completion sort to the top of "last activity ↓"
Verdict: ⚠️ Pending (low, cosmetic)
Action Needed: Postgres sorts NULL first in descending order, so a newly created joiner who never logged in lands above active joiners. No current data triggers this (all 3 joiners have logged in).
- [x] BUS-016a `ordering=F("last_activity").asc(nulls_first=True)`. Declared ascending because the admin reverses it for "newest first", which then puts empty values last (declaring `desc` would make the sort arrows backwards).

BUS-OK (verified good):
- `completed / total` agree: both only count **active** materials. Checked live: angie.ong 0/10, chris.goh 2/10, john.chen 10/10. Deactivating a material no longer pushes the count past the total (3 progress rows point at inactive materials today).
- The extra `progress → material` join is a foreign key (one row each), so completed counts don't double.
- `GREATEST(last_login, MAX(completed_at))` ignores NULLs on Postgres (the only supported database). A joiner who has logged in but completed nothing shows their login time (angie.ong 2026-08-05).
- Frontend login updates `last_login` (Django's `user_logged_in` receiver is connected; checked against chris.goh's live data).
- Staff are still excluded (`is_staff=False`), so admin logins never show up as joiner activity.
- CSV export is unchanged and still lists every progress row, including inactive materials. That's intended as the historical record.

Gate: **PASS**, no blocker. 2 low items waiting for your decision.

Fix (2026-09-14): column now "Last login / completion"; ordering `asc(nulls_first=True)` → newest-first reverses to `desc nulls_last` (verified via `reverse_ordering()`); both sort directions 200 with correct order live. Tests 37/37.

Gate: **PASS**, no blocker, nothing pending.

## QA check — T6.8 congratulations popup — 2026-09-15

BUS-017: any change to the active material count shows the popup again
Verdict: ⚠️ Pending (low)
Action Needed: the "seen" key is `onboard-congrats-<user>-<total>`. If HR deactivates a material (10→9), a joiner who already finished and saw the popup sees it again. Adding a material that the joiner then completes also shows it again, which is intended.
- [x] BUS-017a decide: (a) accept, since it's rare and harmless (recommended), or (b) key on user id only, so it never shows twice, even after new materials.

BUS-018: "seen" key stays in a shared browser after logout
Verdict: ⚠️ Pending (low)
Action Needed: after logout, `localStorage` keeps `onboard-congrats-25-10` (verified). Someone on the same device could tell that user id 25 finished 10 materials. There are no names, and a different joiner on that browser does **not** get the popup (verified).
- [x] BUS-018a decide: (a) accept (recommended, since ids only and on that device only), or (b) clear `onboard-congrats-*` keys on logout.

BUS-OK: `done` can't exceed `total` (`unique_user_material_progress` constraint, both counts active-only). Staff get no `topbar`, so no popup. A failing quiz retake never downgrades a completion (BUS-003), so a joiner can't drop out of "all done" and back in. Locked materials count on both sides.

Gate: **PASS**, no blocker. 2 pending (BUS-017, BUS-018, both low, decisions).

### Decision — 2026-09-15 (user-approved: BUS-017a, BUS-018a)
- BUS-017 ✅ accepted: the popup may show again when the active material count changes. No code change.
- BUS-018 ✅ accepted: the seen-key (user id + count) stays in device-local storage after logout. No code change.

Gate: **PASS**, no open items.

## QA check — T6.9 ribbon burst — 2026-09-15

BUS-OK (verified live): the seen-key is written only when the popup actually opens, so an interrupted burst is never counted as seen. Two tabs loaded together both celebrate once (harmless, same as T6.8). An incomplete joiner gets no ribbons. The server-side "all complete" rule is unchanged (T6.8 BUS-OK).

Gate: **PASS**, no open items.

## QA check — ROB-008 fix (seen-key bumped to v2) — 2026-09-15

BUS-019: old v1 seen-keys stay in browser storage
Verdict: ⚠️ Pending (low)
Action Needed: browsers that saw the T6.8 popup now hold both `onboard-congrats-<user>-<total>` (unused) and `onboard-congrats-v2-...`. It's a few bytes, device-local only, and has the same exposure already accepted in BUS-018.
- [x] BUS-019a decide: (a) accept (recommended), or (b) remove the old key when writing v2 (one line).

BUS-OK (verified live, real flow): joiner at 9/10 → opens last material → **Mark complete** → redirected to checklist → 24 ribbons at 1.15s, popup at 1.75s, count "10 of 10", v2 key written only when the popup opens. Reload shows nothing, so once per browser holds. Another joiner in the same browser gets nothing (0/10, no dialog). The key still includes user id and total, so the new-material rule (BUS-017) is unchanged.
- Note for later: any future change to the celebration that should replay must bump the key version again (template comment says so). The quiz → result → checklist path lands on the same checklist code but is untested live (the only quiz is inactive, same as COM-017).

Gate: **PASS**, no blocker. 1 pending (BUS-019, low, decision).

### Decision — 2026-09-15 (user-approved: BUS-019a)
- BUS-019 ✅ accepted: old v1 seen-keys stay in device-local storage. No code change.

Gate: **PASS**, no open items.

---

## T6.11 Image material type: business logic check (2026-09-15)

BUS-020: a tall image unlocks "Mark complete" without scrolling
Verdict: ✅ Correct (accepted 2026-09-15)
Action Needed: PDFs unlock only after scrolling to the end; images unlock as soon as they load. For a long infographic, a joiner can complete it after seeing only the top.
- [ ] BUS-020a put the image in the same 70vh scroll box as PDFs and unlock on reaching the bottom (short images unlock at once, as 1-page PDFs do). This changes an existing element, so it needs confirmation.
- [x] BUS-020b **Accepted:** Onboarding images are usually one screen, and it's a UX gate only (the server gate is unchanged).

BUS-021: completion, lock, quiz and export rules for images
Verdict: ✅ Correct
Action Needed: None. `mark_complete` / `quiz` / T6.5 lock checks are type-independent; an image material can have a quiz; topbar counts and CSV include it. `remove_file_view` on an image with a URL turns it into a Link (as for PDF/video); on an image without a URL it refuses. File-less image → home redirect (ROB-005 path).

## T6.14 fix: stale file dropped on switch to Link/Video: business logic check (2026-09-15)

BUS-022: new upload silently discarded
Verdict: ✅ Correct (fixed, 022a)
Action Needed: `Material.clean()` drops *any* file when the material has a URL and is a Link, or is a Video and the file isn't a video. That includes a file uploaded in the same save. Verified with the admin form: Video + URL + new `new.pdf` upload, and Link + URL + new upload, both save with no error, and the upload just disappears. Before the fix, Video + .pdf showed an error, so the admin knew. Nothing stored is lost (the upload never reaches MinIO), but the admin's intent is ignored without telling them.
- [x] BUS-022a **Recommended:** only drop a file that's already stored (`self.file._committed`). A new wrong upload goes back to showing an error: the existing extension message for Video, and "Link materials don't use a file." for Link. Add asserts for both.
- [ ] BUS-022b accept: the URL wins and the upload is ignored.
- Verified: tests 41/41 (new asserts for Video and Link). With the admin form, Video + new .pdf shows the extension error, Link + new upload shows "Link materials don't use a file.", Video + new .mp4 saves, and stored PDF → Video + URL still drops the PDF.

BUS-023: file deletion can't hit another material
Verdict: ✅ Correct
Action Needed: None. Uploads use no-overwrite unique names, and `MaterialAdmin.save_as` is False, so no two rows share an object. Material 13's cleared PDF was checked (1 reference) before it was deleted.

## T6.15 hide "Image description" in admin: business logic check (2026-09-15)

BUS-024: hidden, uneditable alt text on existing materials
Verdict: ✅ Correct
Action Needed: None. 0 of 18 materials have a description stored, so no image has leftover alt text that HR can no longer see or change. New descriptions can't be entered, so every image uses its title.

## T6.16 joiner page: incomplete materials + full progress table: business logic check (2026-09-15)

BUS-025: table agrees with the Joiners list count
Verdict: ✅ Correct
Action Needed: None. Both use active materials and `COMPLETED`. Verified on lily.chen with an extra material added (rolled back): changelist `9 / 17`, table 17 rows, 9 Completed. Never-opened materials show "Not started" without creating a `JoinerProgress` row (the P3/P5 lazy-create rule is kept).

BUS-026: locked materials look like plain "Not started"
Verdict: ✅ Correct (fixed 2026-09-15, was ⚠️ Pending)
Action Needed: A material the joiner can't open yet (T6.5 lock) shows as "Not started", the same as one they skipped. HR can't tell "blocked by chapter" from "hasn't bothered".
- [x] BUS-026a optional: append "· locked" to the status when `Material.is_locked_for(joiner)`. Compute it once per chapter as `checklist()` does, not per row. Or accept as is.

BUS-027: inactive materials' progress hidden on the joiner page
Verdict: ✅ Correct (accepted)
Action Needed: None. For example, john.chen's `viewed` row for the inactive "Instruction" link is no longer listed (the old inline showed it). This matches the `X / total` count, which ignores inactive materials. The row is kept in the DB and is still in the CSV export.
- Fixed: `JoinerAdmin._active_progress` works out the lock state once per chapter, using the same rule as `checklist()` (T6.5 + BUS-009). A material that is locked for this joiner right now gets " · locked" after its status ("Not started · locked", or "Viewed · locked" if it was opened before the chapter re-locked) in both the progress table and the incomplete list. No extra queries per row. `LockedMaterialTests` checks: no suffix while the chapter is open, suffix on both locked materials once it re-locks, never on unlocked ones. Tests 41/41.
