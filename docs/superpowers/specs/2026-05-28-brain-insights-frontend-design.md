# Brain Insights Frontend — Design Spec

**Status:** design-locked, awaiting implementation
**Created:** 2026-05-28
**Target version:** v0.11.0 (minimum slice) → v0.11.1-2 (analytics + graph)

## Goal

A local web frontend for the agent-brain — a single-glance instrument panel that surfaces the brain's state to the human user. The agent uses the CLI / hooks; the human uses this UI to inspect what the agent has captured and how it's performing.

## Aesthetic direction: "Brain Telescope" (v2 — minimal redesign)

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

## Implementation tech (locked)

Per the spec doc (separate Phase 3d section):

- **Server:** FastAPI + Jinja2
- **Interactivity:** HTMX 2 + Alpine.js 3 (tiny client state)
- **Styling:** Tailwind CDN with custom config inline OR plain CSS with the tokens above
- **Charts:** Chart.js (CDN, no build step)
- **Graph:** Cytoscape.js (CDN, future v0.11.2)
- **Fonts:** Google Fonts CDN (Fraunces, Manrope, JetBrains Mono)

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

## Mockups

Working HTML mockups bundled at:

- `frontend-design/mockups/dashboard.html`
- `frontend-design/mockups/sources.html`
- `frontend-design/mockups/source-detail.html`
- `frontend-design/assets/styles.css` (shared)

These are static HTML with seeded data — no backend needed. Open in a browser to preview the design before implementation begins.

## Out-of-scope (explicitly)

- Light theme
- Mobile responsive (laptop browser is target)
- Multi-tenant
- Editor for capturing new sources (use the CLI)
- Real-time sockets (polling at 10s for dashboard is fine)
- User accounts / login
- Themes / customization
