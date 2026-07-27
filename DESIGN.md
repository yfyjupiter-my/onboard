# DESIGN.md — Onboard Visual Design System

**Theme: Warm Welcome** — teal + amber on warm paper. Human, calm, trustworthy; corporate without being sterile. Extracted from `themes.html` (Set B). Source of truth for all joiner-facing UI (Django templates + Tailwind + htmx). HR/IT side stays Django admin — not themed here.

---

## 1. Color System

| Token | Hex | Role |
|---|---|---|
| `--bg` | `#FBF7F0` | App background (warm paper) |
| `--surface` | `#FFFFFF` | Cards, top bar, inputs, media chrome |
| `--text` | `#25201B` | Primary text |
| `--muted` | `#8A7D6D` | Secondary text, labels, captions |
| `--primary` | `#0F766E` | Buttons, links, progress fill, focus ring, brand mark |
| `--primary-ink` | `#FFFFFF` | Text/icon on primary |
| `--accent` | `#D97706` | Amber — "to do" / attention tags, secondary CTA only |
| `--line` | `#ECE3D6` | Borders, dividers |
| `--ok` | `#0F766E` | Success / completed (same teal — keep the palette tight) |

Status tag colors derive from tokens via `color-mix` (12% tint bg, 45% border):
- **Done** → `--ok` teal · **To do / Quiz** → `--accent` amber · **Neutral** → `--muted`.

Rules:
- Body text on `--surface`/`--bg` clears 4.5:1. Never put `--muted` on `--accent`.
- Color is never the only signal — pair every status color with an icon or label.
- No gradients, no colored shadows (flat design).

---

## 2. Typography

**Optical Grotesque** — Bricolage Grotesque titles + Inter body. Both vendored as local files under `web/static/fonts/` (`bricolage.woff2`, the true variable font: `opsz` 12–96, `wght` 200–800, `wdth` 75–100; `inter.woff2`); **no CDN import**, no external requests (COM-003).

| Use | Font | Weight | Size |
|---|---|---|---|
| Login title | **Bricolage Grotesque** | 800 | 44px |
| Screen titles (`.title`) | Bricolage Grotesque | 800 | 26–34px |
| Card headline | Bricolage Grotesque | 800 | 19px |
| Body, UI, buttons, items | **Inter** | 400–600 | 16px |
| Labels / kickers | Inter | 700 | 11px, uppercase, `.1em` |
| Score numeral | Inter | 700 | 34px, `tabular-nums` |
| Body line-height | — | — | 1.6 |

Title settings: `font-weight:800`, `letter-spacing:-.04em`, `line-height:.95`, `font-optical-sizing:auto`, `text-wrap:balance`.

⚠️ **Never add `font-variation-settings`** to these rules. It outranks `font-weight` and silently resets every axis you don't list to its default — that renders titles at the wrong weight and kills the `<em>` accent. `font-optical-sizing:auto` already drives `opsz` from the font size. Likewise, only the real variable font works: Google's legacy-UA `.ttf` download is a single static instance where `font-weight` does nothing.

**Accent word** — `<em>` inside any title renders as `font-weight:500` + `--primary`, *not* italic. Use it for one word per title (`Welcome <em>Onboard</em>`, `Your onboarding <em>checklist</em>`). The weight drop is the effect; the colour reinforces it.

Kickers are `--accent` amber at 11px/700/uppercase only — amber is 3.1:1, so it never goes on body text. Fallbacks: `"Bricolage Grotesque", system-ui, sans-serif` / `Inter, system-ui, sans-serif`.

> Replaced the original Fraunces + Inter pairing (2026-07-27). Fraunces was the warmth signal; warmth now comes from the palette and radii, with the grotesque carrying a modern, deliberately-designed voice.

---

## 3. Spacing & Radius

- Scale (px): **2 · 4 · 6 · 8 · 10 · 12 · 14 · 18 · 22**. Card padding `22px`; frame padding `18px`.
- Radius: `--radius: 16px` (cards, items, media, top bar), inputs `9px`, buttons `10px`, tags/ticks `99px` (pill). Warm theme is intentionally rounder than the other themes.
- Shadow (single, soft, warm): `--shadow: 0 2px 6px rgba(120,90,40,.08)`.
- Centered card max-width `320px`; page content max-width `1000px`.

---

## 4. Component Styles

Design tokens live on a root/app wrapper; components read the vars.

```css
:root{
  --bg:#fbf7f0; --surface:#ffffff; --text:#25201b; --muted:#8a7d6d;
  --primary:#0f766e; --primary-ink:#fff; --accent:#d97706;
  --line:#ece3d6; --ok:#0f766e; --radius:16px;
  --shadow:0 2px 6px rgba(120,90,40,.08);
}
```

**Card** — `background:var(--surface); border:1px solid var(--line); border-radius:var(--radius); box-shadow:var(--shadow); padding:22px`. Centered variant: `max-width:320px; margin:0 auto`.

**Button** — height 44px, radius 10px, weight 600. Primary: `background:var(--primary); color:var(--primary-ink)`, hover `filter:brightness(1.07)`. Ghost: transparent + `1px var(--line)`, hover `background:color-mix(in srgb,var(--text) 6%,transparent)`. Accent variant for secondary CTA only. `.sm` = 36px / auto width. Focus: `outline:2px solid var(--accent); outline-offset:2px`.

**Input** — height 42px, `1px var(--line)`, radius 9px. Focus: `border-color:var(--primary)` + `box-shadow:0 0 0 3px color-mix(in srgb,var(--primary) 22%,transparent)`. Always paired with a `<label>` (12px, 600, `--muted`).

**Top bar** — surface card, `padding:11px 14px`, flex with `.spacer`. Holds brand + icon-only logout button.

**Brand** — 28px teal rounded-8 mark (check icon) + wordmark, weight 700.

**Icon button** — 34px, `1px var(--line)`, radius 8px, `--muted` icon; hover 6% text tint. **Must** carry `title`/`aria-label` (icon-only).

**Progress** — 8px track (10% text tint) + teal fill, radius 99px. Meta row below: label left, "3 of 5 complete" right, 12px `--muted`.

**Checklist item** — surface card row: 24px tick (pill) + grow (`<b>` title 14px + `<span>` sub 12px muted) + status tag. Tick `.done` = filled teal + white check. Hover: `border-color:var(--primary); translateY(-1px)`.

**Tag** — 11px pill, `.done` teal tint, `.todo` amber tint, neutral muted.

**Media viewer** — bordered surface, `16/10` stage (muted play/file icon + label), bottom bar (top border) with download icon button + status + "Take quiz" button. Real media = presigned MinIO URL; never a public bucket.

**Quiz result** — centered card: 72px teal-tint success badge, Bricolage Grotesque title, 34px teal score numeral, two tags (Passed / Recorded), ghost "Back to checklist" button.

**Icons** — inline SVG only (Lucide-style: check, book, play, file, log-out, download), 24×24 viewBox, `stroke-width:2` (check uses 3). **No emoji.**

---

## 5. Animation

- Transitions **150–200ms** on `color`, `background`, `border-color`, `box-shadow`, `filter`, `transform` only. No width/height animation.
- Item hover lift `translateY(-1px)`; button hover brightness; input focus ring fade.
- Respect `prefers-reduced-motion: reduce` → disable transforms/transitions.

---

## 6. Prohibitions

- ❌ No emoji as icons — SVG only.
- ❌ No gradients, glassmorphism, or colored/heavy shadows (flat, one soft shadow only).
- ❌ No Bricolage Grotesque on body/UI text — titles and card headlines only.
- ❌ No accent-amber for large fills or body text — attention/CTA accents only.
- ❌ No `--muted` for body copy or on colored backgrounds (contrast).
- ❌ No layout-shifting hover (scale that reflows); use `translateY`/color.
- ❌ No hover-only affordances — must work on tap/keyboard; visible focus everywhere.
- ❌ Don't restyle Django admin — theme applies to joiner templates only.
</content>
