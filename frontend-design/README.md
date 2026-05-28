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

## Aesthetic summary

**Brain Telescope** — a dark, refined instrument for observing memory state.

| Token | Value | Why |
|---|---|---|
| Background | `#0a0a0c` | Near-black with cool tint; observatory atmosphere |
| Text | `#ebebef` | Off-white, slight warmth |
| Warm accent | `#d4a14e` | Amber — staleness, warnings (SPARINGLY) |
| Cool accent | `#3d6f73` | Deep teal — healthy, active states |
| Hairline | `#1f1f24` | 1px borders; structure without weight |
| Display | **Fraunces** (variable serif, italic) | Editorial headlines, hero metrics |
| Body | **Manrope** | Modern geometric sans, not generic |
| Mono | **JetBrains Mono** | All numbers, IDs, paths, timestamps |

**No icon library.** Type weight + whitespace + monospace numerals carry hierarchy.

## Key design moves that must survive implementation

1. **Hero metric on dashboard** — single huge Fraunces italic number. The vibe-setter.
2. **Monospace numbers EVERYWHERE.** IDs, counts, timestamps, scores. Instrument-panel feel.
3. **Single-color accents.** Amber means "needs attention." Teal means "healthy / active." Never use both on the same element.
4. **Sparklines, no axes.** Pure Tufte sparkline — 80×24px SVG path. No labels, no legend.
5. **Editorial italic for section descriptions.** Fraunces italic at body size — adds magazine warmth between data blocks.
6. **Subtle film-grain overlay.** A 600-byte SVG noise at 3% opacity. Already implemented in `styles.css`.
7. **Page-load stagger.** 50ms delay between cards. Already implemented.
8. **Hairline rules at 1px exactly.** Not 0.5px (browser inconsistency). Not 2px (too heavy).

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
| Inter / Roboto / system-ui fonts | Use Manrope or Fraunces |
| Tailwind defaults (zinc-900, etc.) | Use the CSS variables from `styles.css` |
| Material icons / Heroicons library | Use type weight + spacing instead |
| Purple gradient backgrounds | Don't |
| Spinning loaders | Use a thin progress bar at page top |
| Light theme toggle | Out of scope; dark only |
| Drop shadows on cards | Use hairline borders only |
| Border-radius > 6px on cards | Sharp-ish rectangles only |

## Verification before merge

- [ ] All 3 mockups render identically (or better) in production HTML
- [ ] Dashboard hero metric is Fraunces italic at 4.5rem
- [ ] All numbers in tables are JetBrains Mono
- [ ] Hairline borders are 1px and color `#1f1f24`
- [ ] Cards animate with stagger on initial load
- [ ] Hover states are 120ms ease-out
- [ ] Film-grain overlay visible at 3% opacity
- [ ] Status pill shows green dot when DB reachable
- [ ] Page loads under 200ms (no CDN fonts blocking render — use `font-display: swap`)
