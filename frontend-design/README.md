# Brain Insights Frontend — Design Handoff

**Created:** 2026-05-28 in v0.10.1 session
**For:** future implementation session (v0.11.0)
**Status:** design-locked; ready for implementation

## What's in this folder

```
frontend-design/
├── README.md                            ← you are here
├── assets/
│   └── styles.css                       ← shared design tokens + page styles
└── mockups/
    ├── dashboard.html                   ← open in browser
    ├── sources.html                     ← open in browser
    └── source-detail.html               ← open in browser
```

Open the mockups in any browser:

```bash
xdg-open frontend-design/mockups/dashboard.html
# or
python -m http.server -d frontend-design 8000
# then visit http://localhost:8000/mockups/dashboard.html
```

The mockups are static HTML/CSS with seeded data. They demonstrate the EXACT design that the production implementation should match.

## How to use in a fresh session

1. Open the mockups to confirm the design direction still feels right.
2. Read the full design spec: `docs/superpowers/specs/2026-05-28-brain-insights-frontend-design.md`.
3. Read the implementation plan: `docs/superpowers/plans/2026-05-28-agent-brain-v0.11.0-frontend.md`.
4. If the design is approved, invoke `superpowers:subagent-driven-development` and execute the plan task-by-task.

## Aesthetic summary (v2 — minimal redesign)

**Brain Telescope** — a dark, restrained instrument panel. Stripe-dashboard minimalism, not magazine-editorial.

| Token | Value | Why |
|---|---|---|
| Background | `#0a0a0b` | Near-black with cool tint |
| Text | `#f0f0f3` | Off-white, slight warmth |
| Warm accent | `#d4a14e` | Amber — staleness, warnings (SPARINGLY) |
| Cool accent | `#4a8a92` | Deep teal — healthy, active states, sparklines |
| Hairline | `#1f1f23` | 1px borders; structure without weight |
| Sans | **system-ui / -apple-system** (SF Pro on Apple) | Native OS font; zero load delay; restrained tool aesthetic |
| Mono | **ui-monospace** (SF Mono on Apple) | All numbers, IDs, paths, timestamps |

**No icon library. No custom display font. No film-grain overlay.** Aesthetic comes from spacing + weight + restraint.

## Key design moves that must survive implementation

1. **Hero metric on dashboard** — single huge sans number at weight 300, 5rem, letter-spaced -0.04em. NO serif, NO italic.
2. **Monospace numbers EVERYWHERE.** IDs, counts, timestamps, scores. With `font-feature-settings: 'tnum'` for tabular alignment.
3. **Single-color accents.** Amber means "needs attention." Teal means "healthy / active." Never use both on the same element.
4. **Sparklines, no axes.** Pure Tufte sparkline — 80×28px SVG path. No labels, no legend.
5. **Quiet `.lede` paragraphs**, not editorial italic. Plain sans at body size, `--fg-2` color.
6. **Page-load stagger.** 40ms delay between cards.
7. **Hairline rules at 1px exactly.** Not 0.5px (browser inconsistency). Not 2px (too heavy).
8. **Letter-spacing tightened slightly** for SF Pro (`-0.005em` body, `-0.025em` display, `-0.04em` hero). On non-Apple systems falls back gracefully.

## Tech stack (locked, no debate)

- **Server:** FastAPI + Jinja2 templates
- **Interactivity:** HTMX 2 + Alpine.js 3 (CDN)
- **Charts:** Chart.js (CDN) — v0.11.1+
- **Graph view:** Cytoscape.js (CDN) — v0.11.2+
- **Fonts:** Google Fonts CDN
- **Build:** NONE. No npm, no node, no bundler.
- **Server launch:** `brain serve` CLI command, default `127.0.0.1:8765`

## What ships in v0.11.0 (minimum slice)

| Page | Why first |
|---|---|
| `/` Dashboard | Visible value immediately; surfaces underuse |
| `/sources` Browser | Closes a real UX gap (CLI source-by-id is slow) |
| `/sources/<id>` Detail | Needed to make the browser useful |
| `brain serve` CLI | Required to launch the server |

Skipped to v0.11.1+:
- Sessions timeline
- Retrieval analytics
- Knowledge graph
- Search-and-recall console
- Hooks dashboard
- Health page

## Anti-patterns to refuse during implementation

| If you find yourself reaching for | Refuse |
|---|---|
| Adding a serif display font (Fraunces, Newsreader, etc.) | Stick with `--font-sans` (system-ui) only |
| Loading Google Fonts at all | NOT NEEDED in v2 — system fonts only, zero CDN |
| Tailwind defaults (zinc-900, etc.) | Use the CSS variables from `styles.css` |
| Material icons / Heroicons library | Use type weight + spacing instead |
| Purple gradient backgrounds | Don't |
| Film-grain or noise overlays | Removed in v2 — too decorative |
| Spinning loaders | Use a thin progress bar at page top |
| Light theme toggle | Out of scope; dark only |
| Drop shadows on cards | Use hairline borders only |
| Border-radius > 6px on cards | Sharp-ish rectangles only |
| Heavy font weights (700+) | Cap at 500 (medium); hero is 300 (light) |

## Verification before merge

- [ ] All 3 mockups render identically (or better) in production HTML
- [ ] Dashboard hero metric is sans, weight 300, 5rem
- [ ] All numbers use `ui-monospace` / SF Mono with `font-feature-settings: 'tnum'`
- [ ] Hairline borders are 1px and color `#1f1f23`
- [ ] Cards animate with stagger on initial load (40ms delay)
- [ ] Hover states are 100-150ms ease-out
- [ ] NO custom font CDN fetches (zero `<link href="fonts.googleapis.com">`)
- [ ] Status pill shows green dot when DB reachable
- [ ] Page loads under 100ms (no font-loading delay)
- [ ] On macOS the page should render in SF Pro automatically — verify by inspecting computed font-family on `<body>`
