# Brain Insights Frontend — Design Spec

**Status:** design-locked on v3.1 (Crimson Matrix), awaiting implementation
**Created:** 2026-05-28
**Target version:** v0.11.0 (minimum slice) → v0.11.1-2 (analytics + graph)

## Goal

A local web frontend for the agent-brain — a single-glance instrument panel that surfaces the brain's state to the human user. The agent uses the CLI / hooks; the human uses this UI to inspect what the agent has captured and how it's performing.

## v3.1 Aesthetic direction: "Crimson Matrix" (Stitch-adopted, CANONICAL)

The current locked design. Generated via Google's Stitch (Crimson Matrix theme) and accepted as the canonical visual identity for v0.11.0. Replaces v1 (Fraunces+Manrope editorial), v2 (system-ui minimal), AND v3-green (Persistent Cognition Protocol). High-contrast dark mode + technical minimalism: deep-black canvas, vibrant crimson primary reserved for primary actions / critical alerts / active status, strict 2px corner radius, JetBrains Mono headlines, Geist body. "Controlled urgency" — the void provides the empty canvas; crimson signals the alarms.

**Canonical source files:**
- `frontend-design/stitch_agent_brain_dashboard/crimson_matrix/DESIGN.md` — token + philosophy manifest
- `frontend-design/mockups/dashboard.html` (from `dashboard_crimson_matrix/code.html`)
- `frontend-design/mockups/sources.html` (from `sources_browser_crimson_matrix/code.html`)
- `frontend-design/mockups/recall.html` (from `recall_interface_crimson_matrix/code.html`)
- `frontend-design/mockups/knowledge.html` (from `knowledge_visualizer_crimson_matrix/code.html`) — v0.11.2 graph
- `frontend-design/mockups/health.html` (from `health_observability_crimson_matrix/code.html`) — v0.11.1 health

> **Gap:** Stitch did not generate a `source_detail_crimson_matrix/` variant. Implementation must compose the source-detail page from the Crimson primitives demonstrated by the other 5 pages (sidebar, topbar, cards, tables, chips, scrollbar). Treat the layout from the green `_v3-green-legacy/source-detail.html` as the layout skeleton; replace all tokens with Crimson Matrix values.

**Visual commitments (non-negotiable):**

1. **Material 3 dark token system — Crimson Matrix palette.** Use the Stitch palette below verbatim. No ad-hoc colors.
2. **Tonal layering, NOT shadows.** Depth comes from `surface-container-lowest` (#0e0e0e) → `…-low` (#1c1b1b) → `…` (#201f1f) → `…-high` (#2a2a2a) → `…-highest` (#353534) stacking. `box-shadow` is prohibited.
3. **1px outlines at `outline-variant` (#5d3f3f).** Hairlines carry a warm reddish-brown tint, not green. 1px exactly. Use `surface-container-highest` (#353534) as the neutral structural border.
4. **Crimson primary** — `primary-container` (#da0037), `primary` (#ffb3b3 — light crimson for text/icons), `primary-fixed-dim` (#ffb3b3), `surface-tint` (#ffb3b3). Reserve `#da0037` for primary actions, critical alerts, and active status only — it must keep its "alarm value." NEVER substitute green / blue / purple.
5. **JetBrains Mono (headlines + labels) + Geist (body) + Material Symbols Outlined (icons).** All via Google Fonts CDN. Headlines are mono (developer-tool aesthetic). Body is sans (legibility under density).
6. **Strict 2px corner radius (0.125rem).** "Micro-softened industrial." More modern than 0px, far more technical than the rounded mainstream. Pills/chips/avatars may use `rounded-full`; everything else stays at 2px.
7. **Ghost-style secondary buttons.** Transparent + 1px `outline-variant` border + `on-surface` text. Fills with `surface-container-highest` on hover. Primary buttons stay solid crimson (`bg-primary-container text-white`).
8. **Inputs focus to crimson border** (`focus:border-primary-container`). Background stays `surface` with 1px `outline-variant`.
9. **Monospace numerals everywhere.** IDs, counts, timestamps, scores all in JetBrains Mono. Since headlines are mono too, tabular alignment is automatic; still apply `font-feature-settings: 'tnum'` defensively.
10. **Custom 4px scrollbars** per page (inline `<style>` block — track `#0e0e0e`, thumb `#444444`, hover `#da0037`). The hover-to-crimson is deliberate signal.
11. **Optional crimson scanline overlay** — `.crimson-scanline` class with `linear-gradient(to bottom, transparent 50%, rgba(218, 0, 55, 0.05) 50%) 0/100% 4px` for CRT atmosphere. Use sparingly on the dashboard hero only.

### v3.1 Color tokens (Tailwind config — extracted verbatim from Stitch Crimson Matrix)

```js
colors: {
  // Surfaces (tonal layering)
  "background":               "#131313",
  "surface":                  "#131313",
  "surface-dim":              "#131313",
  "surface-container-lowest": "#0e0e0e",
  "surface-container-low":    "#1c1b1b",
  "surface-container":        "#201f1f",
  "surface-container-high":   "#2a2a2a",
  "surface-container-highest": "#353534",
  "surface-bright":           "#393939",
  "surface-variant":          "#353534",
  // Outlines (warm reddish-brown tint)
  "outline":                  "#ad8887",
  "outline-variant":          "#5d3f3f",
  // Text
  "on-surface":               "#e5e2e1",
  "on-background":            "#e5e2e1",
  "on-surface-variant":       "#e6bcbc",   // warm pink — heavy use for secondary text
  "inverse-surface":          "#e5e2e1",
  "inverse-on-surface":       "#313030",
  // Primary — vibrant crimson (use sparingly, keep alarm value)
  "primary":                  "#ffb3b3",   // light crimson for text/icons on dark
  "primary-container":        "#da0037",   // signature crimson for actions/alerts
  "primary-fixed":            "#ffdad9",
  "primary-fixed-dim":        "#ffb3b3",
  "surface-tint":             "#ffb3b3",
  "on-primary":               "#680015",
  "on-primary-container":     "#ffebea",
  "on-primary-fixed":         "#400009",
  "on-primary-fixed-variant": "#920022",
  "inverse-primary":          "#bf002f",
  // Secondary — neutral grey (structural / inactive)
  "secondary":                "#c8c6c6",
  "secondary-container":      "#474747",
  "secondary-fixed":          "#e4e2e2",
  "secondary-fixed-dim":      "#c8c6c6",
  "on-secondary":             "#303030",
  "on-secondary-container":   "#b6b5b4",
  "on-secondary-fixed":       "#1b1c1c",
  "on-secondary-fixed-variant": "#474747",
  // Tertiary — alt neutral grey
  "tertiary":                 "#c6c6c7",
  "tertiary-container":       "#6c6d6d",
  "tertiary-fixed":           "#e2e2e2",
  "tertiary-fixed-dim":       "#c6c6c7",
  "on-tertiary":              "#2f3131",
  "on-tertiary-container":    "#f0f0f0",
  "on-tertiary-fixed":        "#1a1c1c",
  "on-tertiary-fixed-variant": "#454747",
  // Error (kept warm pink — must differ from primary visually in context)
  "error":                    "#ffb4ab",
  "error-container":          "#93000a",
  "on-error":                 "#690005",
  "on-error-container":       "#ffdad6",
}
```

### v3.1 Typography (Tailwind config — extracted from Crimson Matrix)

```js
fontFamily: {
  // Headlines + labels = JetBrains Mono (developer-tool aesthetic)
  "headline-lg":        ["JetBrains Mono", "monospace"],
  "headline-md":        ["JetBrains Mono", "monospace"],
  "headline-sm":        ["JetBrains Mono", "monospace"],
  "headline-lg-mobile": ["JetBrains Mono", "monospace"],
  "label-md":           ["JetBrains Mono", "monospace"],
  "label-sm":           ["JetBrains Mono", "monospace"],
  // Body = Geist (legibility under density)
  "body-lg":            ["Geist", "sans-serif"],
  "body-md":            ["Geist", "sans-serif"],
  "body-sm":            ["Geist", "sans-serif"],
},
fontSize: {
  "headline-lg":        ["32px", { lineHeight: "40px", letterSpacing: "-0.02em", fontWeight: "700" }],
  "headline-md":        ["24px", { lineHeight: "32px", letterSpacing: "-0.01em", fontWeight: "600" }],
  "headline-sm":        ["18px", { lineHeight: "24px", fontWeight: "600" }],
  "headline-lg-mobile": ["24px", { lineHeight: "30px", fontWeight: "700" }],
  "body-lg":            ["16px", { lineHeight: "24px", fontWeight: "400" }],
  "body-md":            ["14px", { lineHeight: "20px", fontWeight: "400" }],
  "body-sm":            ["12px", { lineHeight: "16px", fontWeight: "400" }],
  "label-md":           ["12px", { lineHeight: "16px", fontWeight: "500" }],
  "label-sm":           ["10px", { lineHeight: "12px", fontWeight: "500" }],
}
```

Loaded via:

```html
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Geist:wght@400;500;600&display=swap" />
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" />
```

### v3.1 Shape + spacing tokens (Tailwind config)

```js
borderRadius: {
  "DEFAULT": "0.125rem",  // 2px — STRICT default for ALL components
  "lg":      "0.25rem",   // 4px — slightly larger ghosts
  "xl":      "0.5rem",    // 8px — modals
  "full":    "9999px",    // pills, avatars, status chips only
},
spacing: {
  "unit":          "4px",
  "gutter":        "12px",
  "margin":        "16px",
  "container-max": "1440px",
}
```

> **Note on sidebar width:** Crimson Matrix mockups use Tailwind's default `w-64` (256px) for the sidebar instead of a custom `sidebar-width` token. Implementation should match — use `w-64`.

### v3.1 Tech stack (locked, supersedes v3-green)

- **CSS:** Tailwind CDN — `https://cdn.tailwindcss.com?plugins=forms,container-queries`. The full token block above lives inlined in `base.html` as `<script id="tailwind-config">`.
- **Icons:** Material Symbols Outlined (Google Fonts CDN). Inline style: `.material-symbols-outlined { font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24; vertical-align: middle; }`. Filled icons use `style="font-variation-settings: 'FILL' 1;"`.
- **Sans (body):** Geist 400/500/600 (Google Fonts CDN).
- **Mono (headlines + labels + code):** JetBrains Mono 400/500/600/700 (Google Fonts CDN).
- **Server / HTMX / Alpine / Charts / Graph:** unchanged.

### v3.1 Component vocabulary

- **Sidebar** (`fixed left-0 w-64 h-screen bg-surface-container-low border-r border-surface-container-highest`). Brand header at top: 56px tall (`h-14`) with bottom border `border-surface-container-highest`. Brand icon: 32×32 (`w-8 h-8`) `bg-primary-container rounded` square with filled `psychology` Material Symbol in white. Wordmark "AGENT_BRAIN_V1" in JetBrains Mono `headline-sm` `text-primary` `font-bold`. Operator badge under wordmark in `label-sm text-on-surface-variant opacity-60`. Nav rows: full-row link with `px-4 py-3 flex items-center gap-3`. Section captions: `font-label-sm uppercase tracking-widest text-outline opacity-50`. Active row: `bg-primary-container text-on-primary border-l-2 border-primary` — high-impact crimson fill, not a subtle accent. Inactive: `text-on-surface-variant hover:text-on-surface hover:bg-surface-container-highest`.
- **Top bar** — page-level. `h-14` (56px), `bg-surface border-b border-surface-container-highest`, `px-gutter`. Page title in JetBrains Mono `headline-md` `text-on-surface`. Right side: status pill + version chip in `font-label-sm`.
- **Cards** — `bg-surface-container border border-surface-container-highest rounded` (2px). Internal padding `p-gutter` (12px) or `p-margin` (16px). Header strip: 1px `border-b border-surface-container-highest` separating title from content.
- **Hero metric** — single number in JetBrains Mono `headline-lg` (32px / 700 / -0.02em). Below: `body-sm text-on-surface-variant` caption. Optional `.crimson-scanline` overlay for atmosphere.
- **Tables** — zero radius. `border-collapse: collapse`. Header row `label-sm uppercase text-outline` with `border-b border-surface-container-highest`. Data rows: horizontal 1px borders only (`border-b border-surface-container-highest`). NO vertical borders. NO zebra. Data cells `body-md text-on-surface`. Numeric / ID cells `label-md text-on-surface-variant`. Row hover: `bg-surface-container-high`.
- **Status pips / chips** — Alert/Active: `rounded-full bg-primary-container text-white px-2 py-0.5 font-label-sm`. Neutral: `rounded-full border border-surface-container-highest text-on-surface-variant px-2 py-0.5 font-label-sm`.
- **Sparklines** — inline SVG, 80×28 viewBox, single path `stroke="#da0037"` `stroke-width="1.5"` `fill="none"`. No axes, no labels.
- **Buttons** — Primary: `bg-primary-container text-white rounded px-3 py-1.5 font-label-md hover:bg-inverse-primary` (darken). Secondary (ghost): `bg-transparent border border-surface-container-highest text-on-surface rounded px-3 py-1.5 font-label-md hover:bg-surface-container-highest`.
- **Inputs** — `bg-surface border border-surface-container-highest rounded px-3 py-2 font-body-md text-on-surface placeholder:text-outline focus:border-primary-container focus:outline-none`.
- **Filter pills** — `rounded-full border border-surface-container-highest px-2 py-0.5 font-label-sm text-on-surface-variant hover:border-primary-container hover:text-primary`.
- **Scrollbar** — 4px wide, track `#0e0e0e`, thumb `#444444`, hover `#da0037`. Per-page inline `<style>` (or extracted to `app.css`).
- **Optional crimson scanline** — `.crimson-scanline { background: linear-gradient(to bottom, transparent 50%, rgba(218, 0, 55, 0.05) 50%) 0 / 100% 4px; pointer-events: none; }`. Overlay on hero blocks only.

### v3.1 Verification deltas (supersedes v3-green verification list)

- [ ] Tailwind CDN loads + Crimson Matrix theme config applies (body shows `bg-background` #131313)
- [ ] Material Symbols icons render filled/outlined correctly with vertical-align middle
- [ ] JetBrains Mono + Geist both load (no fallback flash)
- [ ] Sidebar is exactly `w-64` (256px); brand header is `h-14` (56px) with bottom border
- [ ] Brand icon is a 32×32 crimson square (`bg-primary-container`) with white filled `psychology` icon
- [ ] Wordmark "AGENT_BRAIN_V1" renders in JetBrains Mono 600 in `text-primary` (#ffb3b3)
- [ ] Active nav row uses full crimson fill (`bg-primary-container text-on-primary border-l-2 border-primary`) — not a subtle accent
- [ ] All headlines + labels in JetBrains Mono; body copy in Geist
- [ ] All numbers/IDs in JetBrains Mono (already mono since headlines are mono — but tabular figures still apply)
- [ ] Hairlines are 1px `surface-container-highest` (#353534) for structural; `outline-variant` (#5d3f3f) only where the warm-tint variant is wanted
- [ ] Cards have NO `box-shadow`; depth from tonal layering only
- [ ] Strict 2px corner radius on ALL non-pill components (default Tailwind `rounded`)
- [ ] Scrollbar is 4px wide with crimson hover thumb
- [ ] Primary buttons are solid crimson; secondary buttons are ghost (transparent + border)
- [ ] Inputs focus to crimson border (`focus:border-primary-container`)

---

## v2 Aesthetic direction (ARCHIVED — superseded by v3)

> Archived for posterity. Do not implement. See `frontend-design/_v2-legacy/` for the prior mockups.

A dark, restrained instrument panel. Stripe-dashboard minimalism, not magazine-editorial.

A dark, restrained instrument panel. Stripe-dashboard minimalism, not magazine-editorial. The brain is a tool; the UI must feel like a quiet developer instrument. Inspired by:

- Stripe's developer dashboard (mono numbers, sparse tables)
- Linear (restrained sans, tight whitespace)
- Apple Console.app / macOS system tools (system-ui typography)
- Edward Tufte small multiples + sparklines

**Visual commitments (non-negotiable):**

1. **Very dark canvas** — `#0a0a0b` (near-black with cool tint). Not pure black; not generic charcoal.
2. **Off-white text** — `#f0f0f3`. Not pure white. Slight warmth.
3. **One warm accent** — `#d4a14e` (amber) — used sparingly for warnings, staleness, "needs attention" indicators.
4. **One cool accent** — `#4a8a92` (deep teal) — used for healthy/active states, sparklines.
5. **Hairline rules** — `#1f1f23` at 1px exactly. Almost not there. Structure without weight.
6. **No icon library.** Type weight + space + monospace numerals carry hierarchy.
7. **Monospace numbers everywhere** — `ui-monospace` (SF Mono on Apple) for IDs, counts, timestamps, scores. Reinforces the "instrument" tone.
8. **Generous whitespace** — pages are mostly empty space with the data nodes given room to breathe.
9. **NO film-grain overlay** (removed in redesign — added visual noise the design didn't need).
10. **Single sans family** — `system-ui` (SF Pro on Apple, system default elsewhere). NO serif. NO custom display font. Aesthetic comes from spacing + weight + restraint, not from typeface drama.

## Color tokens

```css
:root {
  /* Canvas */
  --bg-0:        #0a0a0c;    /* page background */
  --bg-1:        #111114;    /* card / panel background */
  --bg-2:        #17171b;    /* hover / elevated panel */

  /* Foreground */
  --fg-1:        #ebebef;    /* primary text */
  --fg-2:        #9a9aa3;    /* secondary text */
  --fg-3:        #5e5e66;    /* tertiary text, captions */

  /* Lines */
  --line-1:      #1f1f24;    /* default hairline border */
  --line-2:      #2a2a31;    /* hover border */

  /* Semantic accents (use SPARINGLY) */
  --accent-warm: #d4a14e;    /* amber - staleness, warning */
  --accent-cool: #3d6f73;    /* teal - active, healthy, links */
  --accent-cool-bright: #5f9aa3;  /* teal hover */
  --danger:      #c46969;    /* failure, error */
  --success:     #7da37a;    /* fresh capture, embed coverage 100% */
}
```

## Typography (v2 — system-only)

```css
/* All sans uses the OS native UI font.
   On macOS / iOS  → SF Pro (Display + Text)
   On Windows      → Segoe UI
   On Linux        → system default
   Fallback chain to Helvetica Neue / Helvetica then generic sans-serif. */
--font-sans: -apple-system, BlinkMacSystemFont, system-ui, 'Helvetica Neue', Helvetica, sans-serif;

/* Numbers, IDs, paths, timestamps.
   On macOS / iOS → SF Mono
   Fallback to JetBrains Mono / Menlo / Consolas. */
--font-mono: ui-monospace, 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
```

**Why these choices:**
- **system-ui / -apple-system** — zero font-loading delay (no CDN fetch), most minimal possible. On Apple devices renders as SF Pro, which has the exact restrained-tool aesthetic we want. NO custom display font. Aesthetic comes from spacing + weight + restraint.
- **ui-monospace** — same logic for the mono leg. SF Mono on Apple, JetBrains Mono fallback.

**Type scale (v2 — quieter):**

| Token | Size | Use |
|---|---|---|
| `--text-hero` | 5rem (80px) | Hero metric on dashboard, weight 300 |
| `--text-display` | 1.875rem (30px) | Page titles, weight 500 |
| `--text-h2` | 1.25rem (20px) | Section headings, weight 500 |
| `--text-h3` | 0.9375rem (15px) | Subsection / card titles |
| `--text-body` | 0.875rem (14px) | Body text |
| `--text-mono` | 0.8125rem (13px) | Mono / tabular |
| `--text-small` | 0.75rem (12px) | Captions, eyebrows |

**Type weight rules:**
- Hero metric: **300** (light) — large numbers shouldn't shout
- Page titles: **500** (medium)
- Card titles + table headers: **500** (medium), uppercase 0.04em letter-spaced
- Body: **400** (regular)
- Card values: **400** (regular) at 2rem

**Line heights:** display 0.95, body 1.5, mono 1.5.

**Tabular numerals:** every numeric value uses `font-feature-settings: 'tnum'` so digits align in tables.

**Letter-spacing:** body text `-0.005em` (slight tightening for SF Pro), display `-0.025em`, hero `-0.04em`.

## Spacing scale

Use a single 4px base unit. Tokens:

| Token | Value |
|---|---|
| `--s-1` | 4px |
| `--s-2` | 8px |
| `--s-3` | 12px |
| `--s-4` | 16px |
| `--s-5` | 24px |
| `--s-6` | 32px |
| `--s-7` | 48px |
| `--s-8` | 64px |
| `--s-9` | 96px |
| `--s-10` | 128px |

## Layout patterns

### Page grid

12-column grid at max-width `1440px`, centered. Gutter `var(--s-5)` (24px). Margin: `var(--s-7)` (48px) on each side at desktop.

### Sidebar navigation

Left sidebar: `240px` wide. Sticky. Background `var(--bg-1)`. Hairline divider at `var(--line-1)`. Items styled as:

```
PROJECTS      ← Manrope, --fg-3, uppercase, letterspaced 0.08em, --s-3 padding
  brain       ← Manrope semibold, --fg-1, --s-2 padding, hover --bg-2
  hpe-rag     ← Manrope regular, --fg-2, --s-2 padding, hover --bg-2

INSIGHTS      ← same caption style
→ Dashboard   ← active item gets a 2px teal left border + --fg-1 + --bg-2 bg
  Sources
  Sessions
  Retrieval
  Hooks
  Health
```

### Top bar

`64px` height. Title (Fraunces display, smaller — 1.5rem). Right-aligned: small status pill ("connected · v0.10.1"), version mono tag.

### Cards

Used everywhere for metric groupings. Spec:

```css
.card {
  background: var(--bg-1);
  border: 1px solid var(--line-1);
  border-radius: 6px;     /* small, not rounded */
  padding: var(--s-5);
}

.card:hover {
  border-color: var(--line-2);
}
```

### Hero metric block

Top of dashboard. Single LARGE number in Fraunces 4.5rem, italic option turned on. Below it: small Manrope caption with delta vs previous period (e.g., "+12 this week").

### Tables

The source browser is a table. Spec:

```css
table {
  width: 100%;
  border-collapse: collapse;
}
th {
  text-align: left;
  font-family: 'Manrope';
  font-weight: 600;
  font-size: 0.75rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--fg-3);
  padding: var(--s-3) var(--s-4);
  border-bottom: 1px solid var(--line-1);
}
td {
  padding: var(--s-4);
  border-bottom: 1px solid var(--line-1);
  font-family: 'Manrope';
  color: var(--fg-1);
}
td.mono {
  font-family: 'JetBrains Mono';
  font-size: 0.875rem;
  color: var(--fg-2);
}
tr:hover {
  background: var(--bg-2);
}
```

### Sparklines / tiny charts

For "captures over last 30 days" type micro-charts. SVG inline, 80×24 px, single hairline path at `var(--accent-cool)`. No axes, no labels. Pure Tufte sparkline.

## Motion

Restrained. Use these rules:

1. **Page load:** stagger reveal of card grid — 50ms delay between cards, 200ms transition. Fade-up `translateY(8px) → 0`.
2. **Hover states:** 120ms ease-out on borders and text colors.
3. **Number tickers:** when a metric updates from polling, animate the digits with a 300ms ease-out using a CSS counter or simple JS interpolation.
4. **Modal / drawer:** slide-up from bottom, 200ms `cubic-bezier(0.16, 1, 0.3, 1)`.
5. **NO** spinning loaders. Use a thin progress bar at the top edge of the page during fetches.

```css
@keyframes fade-up {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}
.card { animation: fade-up 300ms ease-out backwards; }
.card:nth-child(1) { animation-delay: 0ms; }
.card:nth-child(2) { animation-delay: 50ms; }
.card:nth-child(3) { animation-delay: 100ms; }
/* etc */
```

## Texture / atmosphere

A single tiny `noise.svg` SVG-based grain. Apply as a fixed background-image over the body with `opacity: 0.03`. NOT a noisy PNG — that adds weight to the page. SVG is ~600 bytes.

```html
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
  <filter id="n">
    <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2"/>
  </filter>
  <rect width="100" height="100" filter="url(#n)" opacity="0.4"/>
</svg>
```

## Page inventory (v0.11.0 minimum slice)

| Page | Path | Status |
|---|---|---|
| Dashboard | `/` | v0.11.0 |
| Sources | `/sources` | v0.11.0 |
| Source detail | `/sources/<id>` | v0.11.0 |
| Sessions | `/sessions` | v0.11.1 |
| Retrieval analytics | `/retrieval` | v0.11.1 |
| Knowledge graph | `/graph` | v0.11.2 |
| Search console | `/console` | v0.11.2 |
| Hooks dashboard | `/hooks` | v0.11.2 |
| Health | `/health` | v0.11.1 |

### Dashboard

Hero metric: total captures (single huge Fraunces number). Underneath: "+N this week" caption.

Below in a 3-column grid:

1. **Capture cadence** — sparkline of captures per day last 30d. Top: count by kind (decisions / gotchas / patterns / notes).
2. **Compliance** — under-captured sessions last 30d (number), thin sessions (number), strict_mode badge (active/inactive). Color-coded: amber if any > 0.
3. **Staleness** — stale sources broken down (changed / missing / untracked) with mono counts. Link to "/sources?filter=stale".

Second row, 2-column:

4. **Recent failures** — top 5 active `failure_memories` with `retry_count`. Each is clickable → source detail.
5. **Embedding coverage** — single sparkline + percentage. Hover shows "X of Y substantive sources embedded."

### Sources browser

Search bar at top (Manrope, --bg-1 background, no border, hairline-bottom underline). Filters as pill chips: `kind=*`, `project=*`, `embedded=*`, `provenance=*`, `valid=*`. Filter chips can be removed.

Table columns:
- ID (mono, --fg-2, small)
- Kind (Manrope semibold)
- URI (Manrope, truncated, ellipsis)
- Content preview (Manrope, 1-line ellipsis, --fg-2)
- Created (mono, relative date, --fg-3)
- Embedded (single ● indicator — teal if yes, --fg-3 if no)
- Stale (amber ▲ indicator if true)

Click row → source detail page.

### Source detail

Header: source ID, kind tag, URI mono. Below: full content in a panel. Sidebar (right): metadata (created_at, updated_at, t_valid_from/to, generation_depth, flags). Provenance section: source_files table with paths + hashes. "Stale: changed" pill if applicable.

Action bar: `[Invalidate]` `[Revise from diff]` (only if stale) `[Open in recall]`.

Tabbed below: `Children` (chunks), `Recall hits` (recent retrieval_log rows that returned this source).

## Implementation tech (v3-locked — see v3 section above for full table)

- **Server:** FastAPI + Jinja2
- **Interactivity:** HTMX 2 + Alpine.js 3 (tiny client state)
- **Styling:** Tailwind CDN with the Stitch theme config inlined in `base.html`
- **Icons:** Material Symbols Outlined (Google Fonts CDN)
- **Fonts:** Geist + Inter + JetBrains Mono (Google Fonts CDN)
- **Charts:** inline SVG sparklines (v0.11.0); Chart.js CDN (v0.11.1+)
- **Graph:** Cytoscape.js (CDN, v0.11.2+)

**No npm. No node. No build step.** Everything ships as static assets bundled with the brain package or pulled via CDN at runtime.

## CLI integration

`brain serve` command:

```bash
brain serve                 # 127.0.0.1:8765
brain serve --port 9000
brain serve --host 0.0.0.0  # multi-machine (no auth — local-network only)
brain serve --reload        # dev: hot-reload templates
```

Single command. Refuses to start if `BRAIN_DB_URL` not reachable.

## Auth

None. Local-only. Document that `--host 0.0.0.0` exposes the brain to the LAN with NO auth — only use in trusted networks.

## Mockups (v3 — Stitch Persistent Cognition Protocol)

Working HTML mockups bundled at:

- `frontend-design/mockups/dashboard.html` (from Stitch `dashboard_dark/code.html`)
- `frontend-design/mockups/sources.html` (from Stitch `sources_browser_dark/code.html`)
- `frontend-design/mockups/source-detail.html` (from Stitch `source_detail_dark/code.html`)
- `frontend-design/mockups/recall.html` (from Stitch `recall_interface_dark/code.html`) — bonus page

There is no shared `styles.css` in v3; each mockup inlines its own Tailwind config + small `<style>` block (scrollbar, icon variation settings). Production extracts the config into `base.html` and serves Tailwind via CDN.

Reference screenshots are alongside each mockup as `.png`.

The v2 mockups + `styles.css` are archived at `frontend-design/_v2-legacy/` and must not be used for implementation.

## Out-of-scope (explicitly)

- Light theme
- Mobile responsive (laptop browser is target)
- Multi-tenant
- Editor for capturing new sources (use the CLI)
- Real-time sockets (polling at 10s for dashboard is fine)
- User accounts / login
- Themes / customization
