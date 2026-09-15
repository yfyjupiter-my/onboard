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

---

## QA check — Compliance & Accessibility, joiner UI + data retention — 2026-09-14
Scope: `base.html`, `_topbar.html`, `registration/login.html`, `checklist.html`, `material.html`, `quiz.html`, `app.css`; log and session retention, erasure.

COM-007: PDFs are canvas images only, so their text is invisible to screen readers
Verdict: ✅ Correct (fixed)
Action Needed: `material.html` renders each PDF page with PDF.js into a bare `<canvas>`, with no text layer and no accessible name. A screen reader announces nothing, and the text can't be selected, searched or reflowed when zoomed (WCAG 1.1.1 / 1.4.5, Level A/AA). The `#pdfview` scroll box also has no `tabindex`, so in Safari keyboard users can't scroll it, which means they can't reach the end and "Mark complete" stays locked.
- [x] COM-007a give `#pdfview` `tabindex="0"` + `role="region"` + `aria-label="{{ material.title }} (PDF)"`, and give each canvas `role="img" aria-label="Page n of N"`.
- [x] COM-007b **new element, needs confirmation:** add an "Open PDF in browser viewer" link (the presigned `file_url`, sandbox rules unchanged) under the viewer, so screen-reader users get the native, accessible PDF view. Alternative: turn on PDF.js's text layer (more code, plus vendoring `pdf_viewer.css`).

COM-008: a disabled "Mark complete" button gives no reason
Verdict: ✅ Correct (fixed)
Action Needed: the button is disabled with `:disabled="!reviewed"`, and no text says what unlocks it. Screen-reader users hear only "dimmed". Sighted users also have to guess that they need to scroll the PDF or watch the video to the end (WCAG 3.3.2).
- [x] COM-008a add a short hint next to the button, shown while locked ("Scroll to the end to enable" / "Watch to the end to enable" / "Loading…" for links), and point the button at it with `aria-describedby`. **New text element, needs confirmation.**

COM-009: videos have no captions
Verdict: ✅ Correct (fixed)
Action Needed: `<video>` has no `<track kind="captions">`, and `Material` has nowhere to store a caption file. WCAG 1.2.2 (Level A) requires captions for prerecorded video with audio, which matters for deaf or hard-of-hearing joiners and for anyone watching without sound.
- [x] COM-009a decide: (a) add an optional `Material.captions` WebVTT file (MinIO, presigned like the video) plus `<track>`, which is a new field and migration; or (b) policy only: HR uploads videos with burned-in captions, noted in README Step 5. (b) needs no code.

COM-010: the "Signing you in…" status is never announced
Verdict: ✅ Correct (fixed)
Action Needed: `#login-loading` has `aria-hidden="true"` on the container. That hides its child `<p role="status">`, so the 3-second hold after pressing Log in is silent for screen-reader users.
- [x] COM-010a remove `aria-hidden="true"` from `#login-loading` only. Its decorative children (ring, orbits, mark) already have their own `aria-hidden`.

COM-011: login errors aren't announced
Verdict: ✅ Correct (fixed)
Action Needed: after a failed login the page re-renders with `<p class="tag todo">Please enter a correct username…</p>`. There's no `role="alert"`, and the message isn't linked to the fields, so a screen reader doesn't read it (WCAG 3.3.1 / 4.1.3).
- [x] COM-011a add `role="alert"` to the error `<p>` in `registration/login.html`.

COM-012: container logs keep client IPs and staff usernames forever, with no size limit
Verdict: ✅ Correct (fixed)
Action Needed: Docker uses the `json-file` driver with an empty `LogConfig` (no `/etc/docker/daemon.json`, no compose `logging:`). The nginx access log (client IP, path, user agent) and the `core` export audit line (staff username) go to stdout and are never rotated. That's personal data kept without any time limit (GDPR storage limitation), and unbounded disk use.
- [x] COM-012a compose: one shared `x-logging: &logging {driver: json-file, options: {max-size: "10m", max-file: "5"}}` and `logging: *logging` on all 4 services. Trade-off: this also caps the COM-004 export audit trail (~50 MB per service). If exports must be auditable longer, ship logs to a retained store and note that in README.

A11y and compliance (verified good):
- `<html lang="en">`. Global `prefers-reduced-motion` switches off every animation (`app.css:129`), and the login typewriter and loader also have their own reduced-motion rules.
- Focus is visible: tiles and buttons have a 2px `--accent` outline on `:focus-visible`; inputs change border colour on focus.
- The quiz is fully native: `<fieldset>`/`<legend>` per question, radios wrapped in `<label>`, `required`, keyboard-operable.
- Link iframes and the fallback iframe have a `title`. Locked tiles are non-interactive `div`s with a text reason (not colour alone). Chapter landmarks and headings are fine (COM-006 note). Contrast tokens were fixed in COM-006.
- Login inputs have `<label for>`.
- Erasure: deleting a `User` cascades to `JoinerProgress` (`on_delete=CASCADE`). Their session rows then hold only a dead user id and are purged by `clearsessions` (ROB-001). CSV copies outside the system are covered by the README handling note (COM-005).
- Sessions last 2 weeks (Django default) and expired rows are purged on start and by daily cron.

Gate: **PASS**, no blocker for internal use.

### Fixes applied — 2026-09-14 (user-approved: COM-007a/b, COM-008, COM-010, COM-011, COM-012, COM-009 option b)
- COM-007 ✅ `#pdfview` gets `tabindex="0" role="region" aria-label="<title> (PDF)"`; each canvas gets `role="img" aria-label="Page n of N"`. New **"Open PDF in browser viewer"** link (new tab, `rel=noopener`), presigned with `ResponseContentType=application/pdf`. Verified live against an HTML file uploaded as "pdf": the plain presign serves `text/html`, the forced link serves `application/pdf` + nosniff, so the link can't become a same-origin HTML page (SEC-010 holds). Probe object deleted.
- COM-008 ✅ a hint next to "Mark complete" while it's locked ("Scroll to the end of the document…" / "Watch the video to the end…" / "Enables once the page has loaded"), hidden via `x-show` once reviewed; the button has `aria-describedby="mc-hint"`.
- COM-009 ✅ option (b): README Step 5 requires burned-in captions for videos. No code or schema change.
- COM-010 ✅ `aria-hidden` removed from `#login-loading` (it's still `hidden` until submit; decorative children keep their own `aria-hidden`).
- COM-011 ✅ `role="alert"` on login error messages.
- COM-012 ✅ `x-logging` anchor (`json-file`, `max-size 10m`, `max-file 5`) on all 4 services. `docker inspect` confirms the LogConfig on db, minio, web and nginx. The COM-004 export audit trail is now capped at ~50 MB of web logs; ship logs elsewhere if longer retention is needed.
- Tests: `manage.py test core` 35/35 (+3: `test_locked_button_explains_itself`, `test_pdf_has_accessible_open_link_forced_to_pdf`, `test_login_error_is_announced`).

Gate: **PASS**, nothing pending.
## QA check — T6.7 top bar (option B) — 2026-09-15

Scope: `_topbar.html`, `.topbar` CSS, `core.context_processors.topbar_progress`. Probed live (Chromium via nginx :8080, joiner session minted server-side and deleted after).

COM-013: sticky top bar covers keyboard focus when tabbing backwards (WCAG 2.2 SC 2.4.11 Focus Not Obscured)
Verdict: ✅ Correct (fixed)
Action Needed: the browser scrolls a focused element to the viewport top, but the bar comes back on scroll-up and sits over it. Reproduced on the checklist at 1280×500: Shift+Tab put **5 tiles** under the visible bar (tile top −1px, bar bottom 61px), so the focus ring can't be seen.
- [x] COM-013a add `html{scroll-padding-top:80px}` to `app.css` (one line; focus/anchor scrolling then stops below the bar).

COM-014: on screens under 560px the "N of M complete" text is `display:none`, and the rail is `aria-hidden`
Verdict: ✅ Correct (fixed, option a)
Action Needed: on phones the material/quiz/result pages give no progress in text, to sighted users or screen readers. The checklist still has per-chapter counts. Pick one:
- [x] COM-014a (recommended) hide the count visually but keep it for screen readers (clip pattern instead of `display:none`), or
- [ ] COM-014b accept it (the rail is decorative; the checklist carries the numbers).

COM-015: the brand link's accessible name is "Welcome back chris.goh", not where it goes (home/checklist)
Verdict: ✅ Correct (accepted)
Action Needed: none. The same was true of the old "Welcome <user>" link. An `aria-label` that drops the visible text would break SC 2.5.3 (Label in Name).

COM-OK (verified good):
- Contrast: the amber 11px/700 kicker is 5.6:1 on white, and the muted 12px count is above 4.5:1 on white.
- 320px width (400% zoom): no horizontal scroll (`scrollWidth` 320), long usernames get an ellipsis, Log out stays visible.
- The bar stays shown while it holds focus (`:focus-within`), so keyboard users can always reach Log out. Without JS it is just a sticky bar.
- Reduced motion: the global rule now also covers `::before/::after`, so the mark ping is off too. The rail and greeting render in their final state.
- Log out has visible text; the icons are `aria-hidden`. `<header>` landmark. Username auto-escaped.
- Motion is transform/opacity only; the entrance plays once per page load, with no loop or flashing (SC 2.3.1).

Gate: **PASS**, no blocker. 2 pending (COM-013, COM-014).

### Fixes applied — 2026-09-15 (user-approved: COM-013a, COM-014a)
- COM-013 ✅ `html{scroll-padding-top:80px}`. Re-probed Shift+Tab through the checklist at 1280×500: page tiles under the visible bar went from 5 to 0. The probe still flagged the bar's own brand link, which is part of the bar and not hidden by it.
- COM-014 ✅ under 560px `.topbar .count` uses the clip pattern (1×1px, `clip-path:inset(50%)`) instead of `display:none`. At 390px it's in the bar's accessibility tree ("N of M complete"), takes no visible space, and nothing scrolls sideways.
- `manage.py test core` 38/38. The probe session was deleted.

Gate: **PASS**, nothing pending.

## QA check — top bar always pinned (hide-on-scroll removed) — 2026-09-15
Probe: Playwright on the live stack (`:8080`), pages `/`, `/material/22/`, `/material/30/`. Viewports 1280×800, 1280×500, 390×844, 740×360 (landscape phone), 320×256 (1280×1024 at 400% zoom). 60 Tab + 60 Shift+Tab steps per page, checking whether focus lands under the bar.

COM-015: at 400% zoom and on landscape phones, the pinned bar takes a large share of the screen, and tall tiles take focus partly under it
Verdict: ✅ Correct (accepted, option a)
Action Needed: the bar is a fixed 61px, which is 24% of the viewport at 320×256 and 17% at 740×360. At 320×256, Tab focus on checklist tiles lands 3–24px under the bar (90/90 steps partial, **0 fully hidden**), so it passes SC 2.4.11 (AA) but not 2.4.12 (AAA). There's no horizontal scroll, so SC 1.4.10 passes. Pick one:
- [x] COM-015a accept: the user asked for the bar to be always pinned, and AA passes.
- [ ] COM-015b unpin on very short screens only, with one line: `@media (max-height:400px){.topbar{position:static}}`. Desktop and portrait phones stay pinned.

COM-016: Shift+Tab onto the material iframe leaves its top 22–27px under the bar
Verdict: ✅ Correct (accepted)
Action Needed: none. At 1280×500 and 740×360, the iframe top is at 34–39px and the bar bottom is at 61px. The browser doesn't scroll because the frame is mostly visible, so focus is not obscured (AA).

COM-017: quiz and result pages not tested live
Verdict: ⚠️ Pending (low)
Action Needed: the only quiz (material 13) is inactive, so its page returns 404 and nothing live could be tested. Those pages use the same `_topbar.html` and CSS, so the risk is low.
- [ ] COM-017a when an active quiz exists, repeat the Tab/Shift+Tab test on `/material/<id>/quiz/` and the result screen (radio focus under the bar).

COM-OK: 0 fully hidden focus in 3 pages × 4 viewports × 120 steps. `scroll-padding-top:80px` (COM-013) still covers the 61px bar. The bar stays at `top=0` after scrolling on every viewport. `scrollWidth` equals the viewport everywhere. There's no motion left on the bar itself (its slide animation is gone).

Gate: **PASS**, no blocker. 2 pending, both low (COM-015, COM-017).

### Decision — 2026-09-15 (user-approved: COM-015a)
- COM-015 ✅ accepted: the bar stays pinned at every screen size, as requested. No code change.

Gate: **PASS**, 1 pending (COM-017, needs an active quiz to test).

## QA check — T6.8 congratulations popup — 2026-09-15

COM-018: popup body text not linked to the dialog
Verdict: ⚠️ Pending (low)
Action Needed: `<dialog>` has `aria-labelledby` but no `aria-describedby`. Focus lands on **Close**, so screen readers announce "Congratulations, you did it! dialog, Close button" and may skip "You've completed all your onboarding materials."
- [x] COM-018a add `id="congrats-desc"` to the paragraph and `aria-describedby="congrats-desc"` to the dialog.

COM-OK (verified live, Chromium): at 320×568 the dialog sits 16px from each edge with no horizontal scroll. Focus opens on Close. The page behind is inert: Tab never reaches a background link or button (it only leaves to the browser UI, which is normal). Esc and Enter on Close both close it without reloading. The emoji is `aria-hidden`. No animation, so reduced motion isn't affected. Contrast uses existing AA tokens (muted, primary on surface).

Gate: **PASS**, no blocker. 1 pending (COM-018, low).

### Decision — 2026-09-15 (user-approved)
- COM-018 ✅ fixed: the dialog has `aria-describedby="congrats-desc"`. Verified live: the description resolves to "You've completed all your onboarding materials."

Gate: **PASS**, 1 pending (COM-017, needs an active quiz to test).

## QA check — T6.9 ribbon burst — 2026-09-15

COM-019: the delayed popup moves keyboard focus mid-interaction
Verdict: ⚠️ Pending (low)
Action Needed: the popup now opens 1.5s after load. A keyboard user who Tabs within that window (reproduced: focus on "Log out" at 1.0s) is moved into the dialog at 1.5s ("Close"). Esc returns them to the page. There's no data loss, and it happens once per browser.
- [x] COM-019a decide: (a) accept, since it's once, short and dismissable (recommended), or (b) open the popup immediately on the first keydown/pointerdown during the delay, so focus moves in response to the user's own action.

COM-OK (verified live): ribbons are `aria-hidden`. The banner's accessibility tree shows only link, count and Log out during the burst. With reduced motion there are no ribbons and the popup opens at once (T6.9 acceptance). WCAG 2.3.1: small moving pieces, no luminance flashes. WCAG 2.2.2: motion ends by itself in under 5s (removed at 3.5s). Ribbons use `pointer-events:none`, so a tile click at 0.6s went through.

Gate: **PASS**, no blocker. 1 pending (COM-019, low, decision). COM-017 still open (needs an active quiz).

### Decision — 2026-09-15 (user-approved: COM-019a)
- COM-019 ✅ accepted: the popup opens 1.5s after load even if the joiner is already Tabbing. It happens once and Esc dismisses it. No code change.

Gate: **PASS**, 1 pending (COM-017, needs an active quiz to test).

## QA check — ROB-008 fix (seen-key bumped to v2) — 2026-09-15

COM-OK (verified live after the real Mark complete flow): the dialog is still named "Congratulations, you did it!", `aria-describedby="congrats-desc"` resolves, and focus opens on Close. The one-time replay for existing joiners has the same properties as the first showing, so COM-018 (fixed) and COM-019 (accepted) stand. No new finding.

Gate: **PASS**, no new items. COM-017 still open (needs an active quiz).

## QA check — T6.10 link-material loading dots — 2026-09-15

COM-020: sighted joiners no longer read *why* Mark complete is disabled on link materials
Verdict: ✅ Correct (accepted)
Action Needed: COM-008 added the sentence so the disabled button explained itself. The dots now say "wait" but not "the button unlocks when this finishes". Screen readers still get the full reason: `aria-describedby="mc-hint"` resolves to "Loading, Mark complete enables once the page has loaded" (verified live). The frame normally loads in about 1s, so the wait is short.
- [x] COM-020a **Recommended:** accept. You asked for this change, and the dots disappear and the button enables within about 1s.
- [ ] COM-020b add `title="Mark complete enables once the page has loaded"` on `#mc-hint` (hover-only, so little help on phones).

COM-021: the dots are faint (opacity 0.35–1 teal on white), and stay at 0.35 under reduced motion
Verdict: ✅ Correct
Action Needed: none. They are decorative (`aria-hidden`). The information is carried by the disabled button and the screen-reader text, so WCAG 1.4.11 non-text contrast doesn't apply.

COM-OK (verified live, Chromium 1280px + 390px): `role="status"` on the hint; three SVGs `aria-hidden`; `.sr-only` text is in the accessibility tree; with reduced motion there are 0 `mc-bob` animations; no horizontal scroll at 390px; the button position is unchanged (y=810 / 872).

Gate: **PASS**, 1 pending (COM-020, low, decision). COM-017 still open (needs an active quiz).

### Decision — 2026-09-15 (user-approved: COM-020a)
- COM-020 ✅ accepted: no code change. Screen readers keep the full reason; the dots are gone in about 1s.

---

## T6.11 Image material type: accessibility check (2026-09-15)

COM-022: image alt text is only the material title
Verdict: ✅ Correct (fixed)
Action Needed: `alt="{{ material.title }}"` names the image but doesn't describe it. An informative image (org chart, floor plan, poster with text) has no real text alternative for screen-reader users (WCAG 1.1.1, Level A).
- [x] COM-022a **Applied (2026-09-15, confirmed):** add an optional `Material.description` field ("Image description"), used as `alt` when set and falling back to the title. Additive migration.
- [ ] COM-022b ~~accept~~ (not chosen)
- Done: `Material.description` ("image description", max 300, optional, with help text in the admin); `<img alt>` uses the description, or the title if it's blank (escaped). Migration `0009_material_description` (additive). Test `test_image_alt_uses_description_else_title`.

COM-023: no way to open a detailed image at full size
Verdict: ✅ Correct (accepted 2026-09-15)
Action Needed: the image is scaled to the card width. On a phone, small text in a large image can only be read by pinch-zooming the whole page. PDFs have an "Open PDF in browser viewer" link (COM-007b); images have nothing similar.
- [ ] COM-023a **new element, needs confirmation:** add an "Open image full size" link under the image (the same presigned `file_url`, with the image type forced so SEC-021 still holds).
- [x] COM-023b accept: pinch-zoom works.

COM-024: hint, icon, layout
Verdict: ✅ Correct
Action Needed: None. The button has `aria-describedby="mc-hint"` ("Enables once the image has loaded"); the failure message is `role="alert"`; the checklist icon is `aria-hidden` and the kicker text says "Image", so colour isn't the only signal; `width:100%;height:auto` doesn't overflow sideways at 400px.

---

## T6.12 image description: accessibility check (2026-09-15)

COM-025: description reaches screen readers; length guidance
Verdict: ✅ Correct (fixed)
Action Needed: `alt` uses the description, or the title when it's blank (tested). A 300-character limit is fine for storage, but alt text is best kept short (around 150 characters), because screen readers read it in one go with no pausing. The help text now says "Image materials only: a short description of what the image shows (about 150 characters)…". Migration `0010` updates the help text only (no SQL).

COM-026: "image description" field shows for PDF/video/link too
Verdict: ✅ Correct (accepted)
Action Needed: None. The label and help text say "Image materials only"; for other types it's stored but unused. Hiding it per type would need admin JS, which isn't worth it.

COM-007b (reverted 2026-09-15, on user request)
Verdict: ⚠️ Pending (accepted gap)
Action Needed: the "Open PDF in browser viewer — works with screen readers, search and zoom" link under the PDF.js viewer was removed. PDF pages are still canvas images with `role="img"` + "Page n of N" labels (COM-007a), but screen-reader users no longer have a route to the PDF's text (WCAG 1.1.1). If needed later, turn on PDF.js's text layer instead (COM-007b alternative).
