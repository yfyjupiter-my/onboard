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
