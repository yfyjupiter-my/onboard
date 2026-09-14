# COM-AUDIT — Compliance & Accessibility

## Phase 4 gate — 2026-07-24

Scope: T4.1 `JoinerProgress` CSV export admin action (`core/admin.py`). No templates/UI added this phase.

COM-001: exported CSV contains PII (names, emails)
Verdict: ✅ Acceptable — access-controlled by design
Action Needed: none in code. Export is a Django admin action, reachable only by `is_staff=True` (HR/IT); joiners have no admin access (verified Phase 3). Columns are the minimum HR needs for onboarding reporting (data minimization holds). Retention/deletion of downloaded files is an operational policy, out of code scope — note in README/Phase 5 if a policy is required.

COM-002: accessibility of the export UI
Verdict: ✅ N/A — no new UI
Action Needed: none. The action renders through Django admin's built-in, accessible action dropdown; Phase 4 added no custom templates. Joiner-facing a11y was covered under Phase 3 templates.

Gate verdict: PASS to Phase 5. No compliance or accessibility blocker.

## Final gate — 2026-07-24

COM-003: Google Fonts loaded from external CDN
Verdict: 🚫 Open — privacy/GDPR + contradicts offline design
Action Needed: `base.html` `<link preconnect fonts.googleapis.com>` + stylesheet makes every page call Google, leaking joiner IPs to a third party (GDPR-relevant; German case law) and breaking the "fully offline runtime" claim (T0.7). Fix: vendor Inter/Fraunces as local `@font-face` under `static/`, or drop to a system font stack. Remove the two external `<link>`s.

A11y (verified good): `<html lang="en">`, viewport meta; login labels `for=` match Django field ids; quiz uses `<fieldset>/<legend>` + `required` radios; iframe has `title`; buttons are real `<button>`. No blocker.

Gate: COM-003 is the open compliance action.

### Final-gate fixes applied — 2026-07-24
- COM-003 ✅ Fixed — Google Fonts CDN removed from `base.html`; Inter + Fraunces vendored locally (OFL) under `static/fonts/` via `@font-face`. Runtime fully offline again; no third-party IP leak.

## QA check — admin joiner export (T6.2 / T6.3) — 2026-07-28

Scope: the widened PII export surface (`c2335de`, `da914f6`) and the two new admin templates. Re-opens COM-001, which was accepted on the narrower T4.1 version.

COM-004: bulk PII export is now one click, with no record that it happened
Verdict: ⚠️ Open — GDPR accountability (Art. 5(2) / 30), low effort to close
Action Needed: T4.1's export required ticking rows, so the operator chose a scope every time. `core_joiner_export` now exports **every joiner matching the current filter — with no filter, the entire joiner table** (name, email, per-material status, score, pass/fail) on a single GET, and nothing is written anywhere: no `LogEntry`, no log line, no count shown to the operator. Django's admin history covers add/change/delete only, so a full staff-side dump of every joiner's training record leaves zero trace. Fix (pick one, both cheap):
- `logging.getLogger(__name__).info("csv export by %s: %d joiners, %d rows", request.user, ...)` in `_csv()` — 2 lines, and container logs are already the audit trail for this stack.
- or `LogEntry.objects.log_action(...)` against the Joiner content type for a trail visible in the admin itself.
Data minimization still holds (columns unchanged, all seven are needed for onboarding reporting); this is about accountability for the wider default scope, not the fields.

COM-005: retention of the downloaded CSV is still undocumented
Verdict: ⚠️ Open — carried from COM-001, now more material
Action Needed: COM-001 accepted "retention is an operational policy, out of code scope" when an export was a handful of ticked rows. With whole-table export a click away, `README.md` should say it plainly in the production section: the CSV contains joiner PII, lives outside the app's control once downloaded, and should be deleted when the reporting need ends. Documentation only, no code.

A11y (verified good):
- Both "Export CSV" controls are real `<a href>` in `object-tools-items` — keyboard-reachable, focusable, styled by the admin's own `.object-tools` rules; no `onclick`-only or `<div role=button>`.
- Link text is self-describing out of context ("Export CSV"), so it reads correctly in a screen-reader link list.
- The changelist grid, the read-only `ProgressInline` and the filter sidebar are stock Django admin markup (labelled fields, `<th scope>` headers, sortable column links) — nothing hand-rolled to break.
- `completed` renders as text `"3 / 7"`, not a bar or colour swatch — no colour-only signalling.

Gate verdict: **PASS** — no accessibility blocker. Two documentation/logging actions open (COM-004, COM-005), neither blocks deploy.

### Fixes applied — 2026-07-28
- COM-004 ✅ Fixed — `_csv()` emits `logger.info("joiner CSV export by %s: %d rows", ...)`, so every export (all three paths) is attributable to a staff username in the container log. Django configures no root logger, so an INFO record from `core` would have been dropped silently — `settings.LOGGING` now adds a console handler for the `core` logger at INFO. Verified: the line appears in the test run and in `docker compose logs web`.
- COM-005 ✅ Fixed — `README.md` Step 8 rewritten for the T6.2/T6.3 admin (it still described the removed ticked-rows-only flow): a table of the three export routes, a note that each one is logged, and a "handle the file" warning that the CSV is joiner personal data to be kept off shared drives and deleted when the reporting need ends.

---

## QA check — T6.4 dashboard chapters — 2026-09-14
Scope: `checklist.html` chapter sections (headings, landmarks, progress tag).

COM-006: amber "Chapter N" label and grey tag text fail WCAG AA contrast
Verdict: ⚠️ Pending — design-token issue, needs DESIGN.md sign-off
Action Needed: measured on the white card (`--surface #fff`):
- `--accent #d97706` 11px/700 "Chapter 1" label: **3.19:1**. AA needs 4.5:1 for small text. The existing card kickers (`.tile .kicker`) use the same token and already fail, so T6.4 repeats an existing issue rather than introducing a new one.
- `.tag.neutral` (`--muted #8a7d6d` on its own 12% tint), used for "0 / 3 done" and "Not started": **3.5:1**, fail.
- `.tag.done` (`--ok #0f766e`): 4.64:1, pass.
Fix: darken the text tokens without changing the look. Use `#b45309` for accent text (5.02:1) and `#6f6457` for muted (4.9:1 on the tag tint, 5.41:1 on `--bg`). These are token edits in `app.css` plus DESIGN.md §1, and they affect all 28 uses of the two tokens. Because DESIGN.md is the approved theme, confirm with the user first. An alternative is to split off an `--accent-ink` token for text only and keep the decorative amber shapes unchanged.

A11y (verified good):
- Heading order: one `h1` for the page, then one `h2` per chapter, with no skipped level. Each `h2` has the accessible name "Chapter 1 Internal information", because the label span sits inside the heading.
- Each chapter is a `<section aria-labelledby>`, so it appears as a named region in a screen reader's landmark list.
- Progress is written out as text ("2 / 5 done"). The green tag colour is extra, not the only signal.
- No new motion, focus traps or interactive controls. Cards are still real `<a>` links in DOM order, chapter by chapter.

Gate: **PASS**, no blocker. COM-006 is an existing token contrast issue, now visible in more places.

### Fixes applied — 2026-09-14
- COM-006 ✅ Fixed (user-approved token change) — `--accent #d97706 → #a84e08` and `--muted #8a7d6d → #6f6457` in `app.css` and DESIGN.md (§1 table, contrast notes, kicker note, token block). Re-measured: amber 5.6:1 on white, 5.2:1 on `--bg`, 4.7:1 on the `.tag.todo` tint; muted 5.8:1 on white, 5.4:1 on `--bg`, 4.9:1 on the `.tag.neutral` tint. All pass AA for small text. The first candidate `#b45309` fixed the kicker but left the "In progress" tag at 4.25:1, so it was darkened one more step. This is a global token swap, so kickers, tags, labels, the focus outline and the decorative shapes all get slightly deeper. Served CSS verified.
