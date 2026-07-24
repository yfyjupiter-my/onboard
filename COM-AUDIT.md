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
