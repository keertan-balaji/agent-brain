# Brain Insights Frontend — Design Handoff (v3.1 Crimson Matrix)

**Created:** 2026-05-28 in v0.10.1 session
**For:** future implementation session (v0.11.0)
**Status:** design-locked on **Crimson Matrix** (Stitch-generated dark theme); ready for implementation

## What's in this folder

```
frontend-design/
├── README.md                              ← you are here
├── stitch_agent_brain_dashboard/          ← canonical Stitch source (Crimson Matrix variant)
│   ├── crimson_matrix/
│   │   └── DESIGN.md                      ← token + philosophy manifest
│   ├── dashboard_crimson_matrix/{code.html,screen.png}
│   ├── sources_browser_crimson_matrix/{code.html,screen.png}
│   ├── recall_interface_crimson_matrix/{code.html,screen.png}
│   ├── knowledge_visualizer_crimson_matrix/{code.html,screen.png}
│   └── health_observability_crimson_matrix/{code.html,screen.png}
├── mockups/                               ← canonical mockups (copied from Stitch)
│   ├── dashboard.html       + dashboard.png
│   ├── sources.html         + sources.png
│   ├── recall.html          + recall.png
│   ├── knowledge.html       + knowledge.png     (v0.11.2 graph)
│   └── health.html          + health.png        (v0.11.1 health)
├── _v3-green-legacy/                      ← prior Persistent Cognition Protocol (archived)
└── _v2-legacy/                            ← prior system-ui redesign (archived)
```

Open the mockups in any browser:

```bash
xdg-open frontend-design/mockups/dashboard.html
# or
python -m http.server -d frontend-design 8000
# then visit http://localhost:8000/mockups/dashboard.html
```

The mockups are static HTML with seeded data. Production templates must match the rendered output exactly.

## Aesthetic summary (v3.1 — Crimson Matrix)

**Agent Brain operator console.** High-contrast dark mode + technical minimalism. Deep-black canvas (`#131313`), vibrant crimson (`#da0037`) reserved for primary actions / critical alerts / active status. JetBrains Mono headlines + labels. Geist body. Strict 2px corner radius. No drop shadows — depth through tonal layering + 1px outlines. Brand personality: aggressive, utilitarian, focused.

### Color tokens (key values — full list inline in each mockup's `tailwind.config`)

| Token | Hex | Use |
|---|---|---|
| `background` / `surface` | `#131313` | Page canvas |
| `surface-container-lowest` | `#0e0e0e` | Deepest tonal layer |
| `surface-container-low` | `#1c1b1b` | Sidebar |
| `surface-container` | `#201f1f` | Cards |
| `surface-container-high` | `#2a2a2a` | Hover / elevated |
| `surface-container-highest` | `#353534` | Structural 1px borders |
| `surface-bright` | `#393939` | Bright accents |
| `outline-variant` | `#5d3f3f` | Warm-tint hairlines |
| `outline` | `#ad8887` | Stronger separators |
| `on-surface` | `#e5e2e1` | Body text |
| `on-surface-variant` | `#e6bcbc` | Secondary text (warm pink) |
| `primary` | `#ffb3b3` | Crimson light — text/icons on dark |
| `primary-container` | `#da0037` | **Signature crimson** — actions/alerts/active |
| `inverse-primary` | `#bf002f` | Darker crimson — button hover |
| `secondary` | `#c8c6c6` | Neutral grey (structural / inactive) |
| `error` | `#ffb4ab` | Failure states |

### Typography (locked)

| Family | Use | Loaded via |
|---|---|---|
| **JetBrains Mono** (400/500/600/700) | Headlines + labels (`headline-lg/md/sm`, `label-md/sm`) | Google Fonts CDN |
| **Geist** (400/500/600) | Body (`body-lg/md/sm`) | Google Fonts CDN |
| **Material Symbols Outlined** | All icons | Google Fonts CDN |

### Shape language

`borderRadius` (Tailwind): `DEFAULT 0.125rem` (2px), `lg 0.25rem` (4px), `xl 0.5rem` (8px), `full 9999px` (pills / avatars only).

**Strict 2px everywhere except pills.** Buttons, cards, inputs, chips all 2px. Avatars + circular status signals can use `rounded-full`.

### Spacing

Custom Tailwind spacing tokens: `unit 4px`, `gutter 12px`, `margin 16px`, `container-max 1440px`. Sidebar uses Tailwind's default `w-64` (256px). Brand header `h-14` (56px).

## Key design moves that must survive implementation

1. **Sidebar fixed at w-64 (256px).** Brand header `h-14` with bottom border. 32×32 crimson square (`bg-primary-container rounded`) holds the filled `psychology` Material Symbol in white. Wordmark "AGENT_BRAIN_V1" in JetBrains Mono `headline-sm` `text-primary`, operator badge in `label-sm text-on-surface-variant opacity-60`.
2. **Active nav uses full crimson fill** (`bg-primary-container text-on-primary border-l-2 border-primary`) — not a subtle accent. The active page is unmistakable.
3. **Section captions in sidebar** use `font-label-sm uppercase tracking-widest text-outline opacity-50`.
4. **Tonal layering, not shadows.** Depth comes from `surface-container-low → surface-container → surface-container-high` stacking, never from `box-shadow`.
5. **No vertical borders in tables.** Horizontal 1px `border-b border-surface-container-highest` only. No zebra striping.
6. **Primary actions = solid crimson.** Hover darkens to `inverse-primary`. Secondary buttons = ghost (transparent + 1px border).
7. **Inputs focus to crimson border** (`focus:border-primary-container`).
8. **Custom scrollbars** — 4px wide, track `#0e0e0e`, thumb `#444444`, hover `#da0037`. The crimson hover is deliberate signal.
9. **Optional crimson scanline overlay** (`.crimson-scanline`) — subtle CRT atmosphere for hero blocks only.

## Tech stack (locked)

- **Server:** FastAPI + Jinja2 templates
- **Interactivity:** HTMX 2 + Alpine.js 3 (CDN)
- **CSS:** Tailwind CDN (`https://cdn.tailwindcss.com?plugins=forms,container-queries`) with theme config inlined per page (extracted to `base.html` in production)
- **Icons:** Material Symbols Outlined (Google Fonts CDN)
- **Fonts:** JetBrains Mono + Geist (Google Fonts CDN)
- **Charts:** Inline SVG sparklines (v0.11.0); Chart.js (v0.11.1+)
- **Graph view:** Cytoscape.js CDN (v0.11.2+)
- **Build:** NONE. No npm, no node, no bundler.
- **Server launch:** `brain serve` CLI command, default `127.0.0.1:8765`

## What ships in v0.11.0 (minimum slice)

| Page | Stitch source | Status |
|---|---|---|
| `/` Dashboard | `dashboard_crimson_matrix/code.html` | v0.11.0 ✅ |
| `/sources` Browser | `sources_browser_crimson_matrix/code.html` | v0.11.0 ✅ |
| `/sources/<id>` Detail | **(no Stitch variant — compose from primitives)** | v0.11.0 ⚠️ |
| `/recall` Recall console | `recall_interface_crimson_matrix/code.html` | v0.11.0 bonus |
| `brain serve` CLI | — | v0.11.0 ✅ |

Bonus from Stitch — slot in v0.11.1/v0.11.2:

| Page | Stitch source |
|---|---|
| `/health` Observability | `health_observability_crimson_matrix/code.html` |
| `/graph` Knowledge visualizer | `knowledge_visualizer_crimson_matrix/code.html` |

> **Source-detail gap:** Stitch did not generate a `source_detail_crimson_matrix/` variant. Implementation must compose the page from the Crimson primitives (sidebar/topbar/cards/tables/chips) demonstrated by the other 5 mockups. Use the green `_v3-green-legacy/source-detail.html` as the layout skeleton, replacing all tokens with Crimson values.

## Anti-patterns to refuse during implementation

| If you find yourself reaching for | Refuse |
|---|---|
| Adding a serif display font | Stick with JetBrains Mono headlines + Geist body only |
| Using Geist for headlines | Headlines are MONO in Crimson Matrix — JetBrains Mono only |
| Tailwind defaults (zinc-900, slate-X, etc.) | Use the Crimson Matrix M3 tokens |
| Heroicons / Feather / Lucide | Use Material Symbols Outlined |
| Substituting blue / green / purple for primary | The crimson `#da0037` IS the brand — never swap |
| Drop shadows on cards | Use tonal layering + 1px outlines only |
| Spinning loaders | Use a thin progress bar at page top |
| Light theme toggle | Out of scope; dark only |
| Border-radius > 2px on most components | Strict 2px — only pills/avatars use `rounded-full` |
| Vertical borders in tables | Horizontal only — `border-b border-surface-container-highest` |
| Zebra-striped tables | No zebra — Crimson Matrix prefers density without striping |
| Overusing crimson | Reserve for primary actions / critical alerts / active state; loses alarm value if everywhere |

## Verification before merge

- [ ] All 5 page mockups (dashboard, sources, source-detail, recall, optional health/knowledge) render identically (or better) in production HTML
- [ ] Sidebar is exactly `w-64` (256px); brand header is `h-14` (56px) with bottom border
- [ ] Brand icon is a 32×32 crimson square with white filled `psychology` icon
- [ ] Wordmark "AGENT_BRAIN_V1" renders in JetBrains Mono `headline-sm` `text-primary` `font-bold`
- [ ] Active nav row uses full crimson fill — `bg-primary-container text-on-primary border-l-2 border-primary`
- [ ] All headlines + labels in JetBrains Mono; body copy in Geist
- [ ] Hairlines are 1px `surface-container-highest` (#353534) for structural; `outline-variant` (#5d3f3f) where warm tint is wanted
- [ ] Cards have NO `box-shadow`; depth from tonal layering only
- [ ] All non-pill components use strict 2px corner radius
- [ ] Scrollbar is 4px wide with crimson hover thumb (#da0037)
- [ ] Primary buttons solid crimson; secondary ghost
- [ ] Inputs focus to crimson border
- [ ] Tailwind CDN, Material Symbols, JetBrains Mono, Geist all load successfully on first render
- [ ] Status pill shows green dot when DB reachable — wait, NO: in Crimson Matrix, healthy status uses neutral grey (`#c8c6c6`) or omitted entirely; only `#da0037` signals alert. Match the mockup convention.
- [ ] Each mockup's `screen.png` matches the rendered HTML side-by-side
