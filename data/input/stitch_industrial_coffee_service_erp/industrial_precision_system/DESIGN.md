---
name: Industrial Precision System
colors:
  surface: '#fcf9f8'
  surface-dim: '#dcd9d9'
  surface-bright: '#fcf9f8'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f6f3f2'
  surface-container: '#f0eded'
  surface-container-high: '#eae7e7'
  surface-container-highest: '#e5e2e1'
  on-surface: '#1c1b1b'
  on-surface-variant: '#414845'
  inverse-surface: '#313030'
  inverse-on-surface: '#f3f0ef'
  outline: '#727974'
  outline-variant: '#c1c8c3'
  surface-tint: '#466558'
  primary: '#153328'
  on-primary: '#ffffff'
  primary-container: '#2c4a3e'
  on-primary-container: '#98b9a9'
  inverse-primary: '#adcebe'
  secondary: '#5e5e5e'
  on-secondary: '#ffffff'
  secondary-container: '#e1dfdf'
  on-secondary-container: '#636262'
  tertiary: '#2d2f2c'
  on-tertiary: '#ffffff'
  tertiary-container: '#434542'
  on-tertiary-container: '#b2b2ae'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#c8eada'
  primary-fixed-dim: '#adcebe'
  on-primary-fixed: '#012016'
  on-primary-fixed-variant: '#2f4d41'
  secondary-fixed: '#e4e2e2'
  secondary-fixed-dim: '#c7c6c6'
  on-secondary-fixed: '#1b1c1c'
  on-secondary-fixed-variant: '#464747'
  tertiary-fixed: '#e3e3de'
  tertiary-fixed-dim: '#c6c7c3'
  on-tertiary-fixed: '#1a1c1a'
  on-tertiary-fixed-variant: '#464744'
  background: '#fcf9f8'
  on-background: '#1c1b1b'
  surface-variant: '#e5e2e1'
typography:
  headline-lg:
    fontFamily: IBM Plex Sans
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: IBM Plex Sans
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.01em
  body-lg:
    fontFamily: IBM Plex Sans
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: IBM Plex Sans
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-caps:
    fontFamily: IBM Plex Sans
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.05em
  label-muted:
    fontFamily: IBM Plex Sans
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  mono-data:
    fontFamily: IBM Plex Mono
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
  mono-total:
    fontFamily: IBM Plex Mono
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
spacing:
  base: 4px
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  gutter: 16px
  margin-mobile: 16px
  target-min: 44px
---

## Brand & Style

This design system is engineered for industrial efficiency and high-stakes accuracy within coffee machine repair logistics. The aesthetic is strictly utilitarian, drawing inspiration from technical blueprints and architectural specifications. It prioritizes information density over visual flair, ensuring that technicians and accountants can parse complex data sets rapidly.

The style is defined by **Industrial Minimalism** and **Brutalist** clarity. It employs a rigid grid, zero-radius corners, and a high-contrast "Ink-on-Paper" palette to reduce cognitive load during long periods of use. There are no decorative elements, gradients, or shadows; the UI relies entirely on structural lines and typographic hierarchy to communicate order.

**Target Audience:** Repair technicians, warehouse managers, and industrial accountants.
**Emotional Response:** Reliability, precision, discipline, and uncompromising clarity.

## Colors

The color palette is derived from technical documentation. The background uses a slightly warm neutral to reduce eye strain, while the primary accent is a deep forest green reserved for terminal actions and financial totals.

- **Background (#F4F4F1):** The primary canvas for the application.
- **Surface (#FFFFFF):** Used for data entry containers and document headers.
- **Ink (#1A1A1A):** The primary text color for maximum legibility.
- **Muted (#5C5C5C):** Used for secondary metadata and auxiliary labels.
- **Line (#D4D4D0):** The exclusive color for 1px structural borders and dividers.
- **Forest (#2C4A3E):** Marks primary actions, "Active" status badges, and final totals.
- **Warn (#8A5A00):** Used for low stock levels or pending approvals.
- **Danger (#8B1E1E):** Used for critical errors, overdue invoices, or mechanical failures.

## Typography

The typography system uses a dual-font approach to differentiate between UI context and raw data.

- **IBM Plex Sans (UI):** Used for all navigational elements, descriptive text, and interface controls. It provides a contemporary, professional tone.
- **IBM Plex Mono (Data):** Used strictly for serial numbers, part IDs, phone numbers, and currency values. The monospaced nature ensures that columns of numbers align perfectly for easy comparison.

**Language Support:** All typography must support the Cyrillic alphabet.
**Hierarchy:** Use `label-muted` for field titles above inputs. Use `mono-total` for final invoice amounts to provide immediate visual distinction from standard body text.

## Layout & Spacing

This design system uses a strict 4px baseline grid. Layouts are constructed to maximize screen real estate on mobile devices while maintaining 44px minimum touch targets for all interactive elements to accommodate use in workshops.

- **Grid Model:** Fluid grid on mobile; fixed-width modular sections on desktop.
- **Mobile (390x844):** 16px outer margins, 16px gutters between information blocks.
- **Density:** Elements are packed tightly. Vertical spacing between related data points should use `sm` (8px), while spacing between different sections uses `lg` (24px).
- **Alignment:** All text and containers must align to the 1px border lines to maintain the "paper form" aesthetic.

## Elevation & Depth

This design system is strictly flat. It rejects all use of shadows, blurs, or Z-axis layering.

- **Tonal Layering:** Hierarchy is achieved solely through color contrast. The background is `#F4F4F1`, and interactive containers or input fields are `#FFFFFF`.
- **Borders:** Every logical section, card, and input is enclosed in a 1px solid border of `#D4D4D0`. 
- **Active States:** Active or selected items are indicated by an increase in border weight to 2px or a color shift to `#2C4A3E`, never by a shadow.
- **Separation:** Use `#D4D4D0` horizontal rules to separate items within a list.

## Shapes

All UI elements—including buttons, input fields, cards, and tags—must have **0px border radius**. Sharp corners communicate the industrial, uncompromising nature of the service. 

- **Structural Integrity:** Use 1px borders for all containers.
- **Buttons:** Rectangular boxes with no rounding.
- **Selection Controls:** Checkboxes and radio buttons must remain square and sharp-edged.

## Components

### Buttons
- **Primary:** Solid `#2C4A3E` fill, white text, 0px radius, 44px height.
- **Secondary:** White fill, 1px border `#1A1A1A`, black text.
- **Mobile CTA:** Primary buttons are pinned to the bottom of the viewport with a background blur or solid `#F4F4F1` backing.

### Input Fields
- **Structure:** 1px border `#D4D4D0`, white background, 44px height.
- **Labels:** 12px `label-muted` text placed exactly 4px above the input box.
- **State:** On focus, the border changes to 1px `#1A1A1A`.

### Data Tables / Lists
- **Rows:** 1px bottom border only.
- **Cells:** Use `IBM Plex Mono` for all numeric values. 
- **Density:** 12px vertical padding for row items.

### Chips & Status Tags
- **Design:** Rectangular, 1px border, no fill. 
- **Typography:** 10px uppercase bold.
- **Colors:** Use Warn, Danger, or Forest for the border and text color based on status.

### Cards
- **Usage:** Used for individual repair tickets or machine profiles.
- **Style:** White background, 1px `#D4D4D0` border, 0px radius. No shadow.