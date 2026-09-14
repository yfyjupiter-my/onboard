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
Verdict: ⚠️ Pending
Action Needed: `admin.site.site_url` defaults to `/`. For a staff user that's the frontend login page, which rejects staff accounts, so the link is a dead end now that the sessions are split.
- [ ] BUS-013a set `admin.site.site_url = None` in `core/admin.py` (hides the link). One line.

BUS-014: a joiner promoted to staff keeps their live frontend session
Verdict: ✅ Correct (accepted)
Action Needed: none. Frontend views don't check `is_staff`, so the promoted account can keep using its existing frontend session until logout. Blocking staff sessions on the frontend was offered for T6.6 and declined. New staff logins at the frontend are still rejected by `JoinerLoginForm`. A staff user demoted to joiner loses admin on the next request (`is_staff` is checked on every request).

BUS-OK (verified good):
- Logging in or out on one portal doesn't affect the other (`SessionIsolationTests`).
- A password change or `is_active=False` still ends sessions on both sides, because the session auth hash and `is_active` are checked on every request whichever cookie is used.
- `/login/?next=/admin/` sends a joiner to the admin login page. There's no bypass.
- The messages cookie is shared (`Path=/`), but the frontend templates never render messages, so admin messages can't leak to the frontend.

Gate: **PASS**, no blocker. Two one-line pending items (ROB-001, BUS-013).
