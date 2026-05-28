---
name: Crimson Matrix
colors:
  surface: '#131313'
  surface-dim: '#131313'
  surface-bright: '#393939'
  surface-container-lowest: '#0e0e0e'
  surface-container-low: '#1c1b1b'
  surface-container: '#201f1f'
  surface-container-high: '#2a2a2a'
  surface-container-highest: '#353534'
  on-surface: '#e5e2e1'
  on-surface-variant: '#e6bcbc'
  inverse-surface: '#e5e2e1'
  inverse-on-surface: '#313030'
  outline: '#ad8887'
  outline-variant: '#5d3f3f'
  surface-tint: '#ffb3b3'
  primary: '#ffb3b3'
  on-primary: '#680015'
  primary-container: '#da0037'
  on-primary-container: '#ffebea'
  inverse-primary: '#bf002f'
  secondary: '#c8c6c6'
  on-secondary: '#303030'
  secondary-container: '#474747'
  on-secondary-container: '#b6b5b4'
  tertiary: '#c6c6c7'
  on-tertiary: '#2f3131'
  tertiary-container: '#6c6d6d'
  on-tertiary-container: '#f0f0f0'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#ffdad9'
  primary-fixed-dim: '#ffb3b3'
  on-primary-fixed: '#400009'
  on-primary-fixed-variant: '#920022'
  secondary-fixed: '#e4e2e2'
  secondary-fixed-dim: '#c8c6c6'
  on-secondary-fixed: '#1b1c1c'
  on-secondary-fixed-variant: '#474747'
  tertiary-fixed: '#e2e2e2'
  tertiary-fixed-dim: '#c6c6c7'
  on-tertiary-fixed: '#1a1c1c'
  on-tertiary-fixed-variant: '#454747'
  background: '#131313'
  on-background: '#e5e2e1'
  surface-variant: '#353534'
typography:
  headline-lg:
    fontFamily: JetBrains Mono
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: JetBrains Mono
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: JetBrains Mono
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
  body-lg:
    fontFamily: Geist
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Geist
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Geist
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  label-md:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
  label-sm:
    fontFamily: JetBrains Mono
    fontSize: 10px
    fontWeight: '500'
    lineHeight: 12px
  headline-lg-mobile:
    fontFamily: JetBrains Mono
    fontSize: 24px
    fontWeight: '700'
    lineHeight: 30px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  unit: 4px
  gutter: 12px
  margin: 16px
  container-max: 1440px
---

## Brand & Style

This design system is built for the "Agent Brain" dashboard—a high-performance, technical environment where speed and precision are paramount. The brand personality is aggressive, utilitarian, and focused. It targets technical operators and developers who require immediate visual feedback and high information density.

The style is a fusion of **High-Contrast Dark Mode** and **Technical Minimalism**. It utilizes a strict 2px radius across all components to maintain a sharp, engineered feel. The emotional response is one of controlled urgency; the deep black background provides a "void" where only critical data, highlighted by vibrant crimson, demands attention. There is no room for decorative fluff; every pixel serves a functional purpose.

## Colors

The palette is optimized for high-contrast legibility in low-light environments. 

- **Primary (#DA0037):** A vibrant crimson reserved for primary actions, critical alerts, and active status signals. It should be used sparingly to maintain its "alarm" value.
- **Secondary (#444444):** A mid-grey used for structural borders, inactive states, and tertiary information.
- **Surface (#171717):** The deep black foundation for the entire UI, ensuring maximum contrast with text and primary accents.
- **Text/Highlight (#EDEDED):** A soft off-white used for primary body copy and headers to reduce eye strain compared to pure white, while maintaining a stark contrast against the black background.

## Typography

This system uses a dual-font approach to emphasize its technical nature. 

**JetBrains Mono** is used for headlines and labels. Its monospaced nature reinforces the "developer-tool" aesthetic and ensures data alignment in dashboards. 

**Geist** is used for body text to maintain high legibility in dense layouts. It provides a clean, neutral contrast to the monospaced headers.

For hierarchy:
- Use **#EDEDED** for all headlines and primary body text.
- Use **#444444** for metadata, captions, and secondary labels.
- Use **#DA0037** for critical status text or inline alerts only.

## Layout & Spacing

The system follows a **high-density fluid grid** model based on a 4px baseline. To maximize the "Agent Brain" utility, white space is minimized in favor of information throughput.

- **Grid:** A 12-column system for desktop, 8-column for tablet, and 4-column for mobile.
- **Gutters:** Tight 12px gutters to keep related data clusters visually connected.
- **Margins:** 16px safe areas on mobile, scaling to 24px or 32px on larger displays.
- **Density:** Elements should be tightly packed. Vertical rhythm is maintained through 4px/8px/12px increments. Use thin borders (#444444) rather than large gaps to separate modules.

## Elevation & Depth

This design system rejects traditional shadows and depth. It uses a **Tonal Layering** and **Bold Outlining** approach to convey hierarchy.

- **Base Level:** The background is #171717.
- **Containers/Modules:** Surfaces sit on the base and are defined by a 1px solid border of #444444. 
- **Active State:** When an element is focused or active, its border color shifts to #DA0037 or a brighter grey.
- **Interaction:** No shadows are used. Depth is communicated strictly through color shifts and 1px border variations. "Overlays" (modals) should use a solid #171717 background with a 2px #444444 border to distinguish them from the background.

## Shapes

The shape language is rigid and precise. A strict **2px corner radius** (0.125rem) is applied to all interactive elements, containers, and cards. This creates a "micro-softened" industrial look that feels more modern than 0px sharp corners but far more technical than standard rounded UI. 

Icons should follow this aesthetic—using square ends and sharp angles where possible, avoiding circular containers unless strictly necessary for brand recognition (e.g., user avatars).

## Components

### Buttons
- **Primary:** Solid #DA0037 background, #EDEDED text. 2px radius. 
- **Secondary:** Transparent background, 1px #444444 border, #EDEDED text.
- **State:** On hover, primary buttons darken slightly; secondary buttons fill with #444444.

### Inputs & Fields
- Background is #171717 with a 1px #444444 border.
- Text is #EDEDED (Primary) or #444444 (Placeholder).
- On focus, the border changes to #DA0037.

### Cards & Modules
- Used for dashboard widgets. 1px solid #444444 border. 2px corner radius.
- Headers within cards should have a subtle #444444 bottom border to separate the title from the content.

### Chips & Status Signals
- **Alert/Active:** Small #DA0037 pill with white text for high-impact signals.
- **Neutral:** 1px #444444 border with JetBrains Mono label text.

### Data Tables
- High density. 1px horizontal borders (#444444). No vertical borders.
- Header row uses `label-sm` in #444444. Row data uses `body-md` in #EDEDED.