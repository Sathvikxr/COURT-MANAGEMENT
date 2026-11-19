# NyayaDesk UI/UX Design System & Architectural Guidelines

> **Version**: 2.0.0 (Linear / Stripe Aesthetic Pass)  
> **Target Audience**: Frontend Engineers, Judicial Tech Designers, Accessibility Reviewers  
> **Primary Stylesheet**: `C:\CourtMS\static\css\design-system.css`

---

## 1. Overview & Design Philosophy

NyayaDesk's UI bridges solemn judicial authority with modern legal-tech SaaS aesthetics inspired by **Linear** and **Stripe**. 

### Core Principles
1. **Precision & Density**: Clean 1px borders, subtle low-contrast dividers, and deliberate whitespace rather than heavy card borders or garish colors.
2. **Typography-First Hierarchy**: Tabular numerals for judicial dates, case numbers, and financial data; crisp neutral typography for UI; restrained serif accents exclusively for institutional dignity (brand mark and formal judicial documents).
3. **Restrained Color Palette**: Deep Navy (`#0B1F3A`) provides institutional grounding; Rich Gold (`#C9A24B`) is used sparingly for accents, focus rings, and primary key indicators; soft semantic tints handle statuses cleanly without visual fatigue.
4. **Fluid Responsiveness**: Seamless experience across 5 core breakpoints (375px, 768px, 1024px, 1440px, and 1920px) with minimum 44px touch targets on mobile.
5. **Formal Print Fidelity**: Built-in `@media print` rules render official High Court bench orders, cause lists, and treasury fee receipts with emblem seals, signature coram blocks, and cryptographic QR token boxes.

---

## 2. Design Tokens

All design tokens are defined as CSS Custom Properties in `:root` and re-mapped for `[data-theme="dark"]`.

### 2.1 Color Palette

#### Neutral Scale (Grayscale)
| Token | Light Mode Value | Dark Mode Value | Intended Usage |
|---|---|---|---|
| `--color-gray-50` | `#F8FAFC` | `#0A0F1D` | Global background canvas |
| `--color-gray-100` | `#F1F5F9` | `#0E1626` | Card background / Secondary fill |
| `--color-gray-200` | `#E2E8F0` | `#1A2438` | Low-contrast borders / Dividers |
| `--color-gray-300` | `#CBD5E1` | `#2D3B55` | Strong borders / Skeleton base |
| `--color-gray-400` | `#94A3B8` | `#64748B` | Placeholder text / Inactive icons |
| `--color-gray-500` | `#64748B` | `#94A3B8` | Muted descriptions / Secondary text |
| `--color-gray-600` | `#475569` | `#CBD5E1` | Regular body copy |
| `--color-gray-700` | `#334155` | `#E2E8F0` | Headings / Subtitles |
| `--color-gray-800` | `#1E293B` | `#F1F5F9` | Prominent titles |
| `--color-gray-900` | `#0F172A` | `#FFFFFF` | Highest emphasis titles / Brand text |
| `--color-gray-950` | `#020617` | `#030712` | Dark accents / Deep shadows |

#### Brand & Accent Colors
| Token | Hex Value | Dark Mode Override | Usage |
|---|---|---|---|
| `--brand-navy` | `#0B1F3A` | `#1A2E4C` | Institutional authority, dark surfaces, sidebar |
| `--brand-navy-light` | `#162E52` | `#243F66` | Sidebar hover, elevated dark containers |
| `--brand-navy-subtle`| `#E8EEF5` | `#121D2F` | Soft navy badge backgrounds |
| `--gold` | `#C9A24B` | `#D4B05C` | Primary accent, CTA borders, active badges, focus |
| `--gold-light` | `#DFBA6B` | `#E5C57E` | Gold hover state |
| `--gold-hover` | `#B58E38` | `#C49B44` | Gold pressed state |
| `--gold-dim` | `#C9A24B22`| `#C9A24B33`| Transparent gold glow, selected item background |

#### Semantic Status Tokens
| Semantic Role | Primary Token | Subtle Background | Border Token | Used For |
|---|---|---|---|---|
| **Success** | `--success` (`#10B981`) | `--success-subtle` (`#ECFDF5`) | `--success-border` (`#A7F3D0`) | Disposed, Approved, Paid, Active |
| **Warning** | `--warning` (`#F59E0B`) | `--warning-subtle` (`#FFFBEB`) | `--warning-border` (`#FDE68A`) | Hearing, Pending, Adjourned, High Risk |
| **Danger** | `--danger` (`#EF4444`) | `--danger-subtle` (`#FEF2F2`) | `--danger-border` (`#FECACA`) | Defective, Returned, Urgent, Failed |
| **Info** | `--info` (`#3B82F6`) | `--info-subtle` (`#EFF6FF`) | `--info-border` (`#BFDBFE`) | Registered, Notice Issued, In-Scrutiny |

---

### 2.2 Typography Scale

- **UI Font Family**: `'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`
- **Monospace & Tabular Numbers**: `'JetBrains Mono', 'SF Mono', Consolas, monospace`
- **Judicial Wordmark & Display Font**: `'Playfair Display', Georgia, serif`

```css
/* Type Scale */
--font-xs:   0.75rem;   /* 12px - Small metadata, timestamps, badge labels */
--font-sm:   0.8125rem; /* 13px - Secondary body, table cells, form labels */
--font-base: 0.875rem;  /* 14px - Primary UI body text, navigation links */
--font-md:   1rem;      /* 16px - Card titles, form inputs, button text */
--font-lg:   1.125rem;  /* 18px - Section headers, modal titles */
--font-xl:   1.375rem;  /* 22px - Dashboard page titles, major headers */
--font-2xl:  1.75rem;   /* 28px - KPI stat numbers, hero subheads */
--font-3xl:  2.25rem;   /* 36px - Hero headline numbers, landing titles */
```

---

### 2.3 Spacing Scale (4px Base Grid)

```css
--space-1:  4px;
--space-2:  8px;
--space-3:  12px;
--space-4:  16px;
--space-5:  20px;
--space-6:  24px;
--space-8:  32px;
--space-10: 40px;
--space-12: 48px;
--space-16: 64px;
```

---

### 2.4 Border Radii & Elevation Shadows

```css
/* Radii */
--radius-xs:  4px;    /* Chips, small tags */
--radius-sm:  6px;    /* Buttons, form inputs */
--radius-md:  8px;    /* Cards, dropdowns, table containers */
--radius-lg:  12px;   /* Modals, large feature cards */
--radius-xl:  16px;   /* Drawers, hero preview containers */
--radius-full: 9999px; /* Status pills, avatar circles */

/* Layered Shadows */
--shadow-xs: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
--shadow-sm: 0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px -1px rgba(0, 0, 0, 0.1);
--shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -2px rgba(0, 0, 0, 0.1);
--shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -4px rgba(0, 0, 0, 0.1);
--shadow-xl: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1);
--shadow-glow-gold: 0 0 0 3px rgba(201, 162, 75, 0.25);
```

---

## 3. Core Component Library

### 3.1 Buttons (`.btn`)
- **Default Height**: 36px (compact desktop) with 8px horizontal padding.
- **Mobile Height**: Enforced `min-height: 44px` on `< 768px` devices for touch target compliance.
- **Variants**:
  - `.btn-primary`: Solid Navy or Gold primary action.
  - `.btn-secondary`: Neutral subtle gray fill with border.
  - `.btn-outline`: 1px border with transparent background.
  - `.btn-gold`: Rich gold background with dark navy text.
  - `.btn-danger`: Red tone for destructive actions (e.g., rejecting an application).
  - `.btn-icon`: Square 36x36px icon-only button with centered SVG.

### 3.2 Form Controls & Floating Labels
- Crisp 1px border (`--color-gray-200`) transitioning to `--gold` on focus.
- Universal `:focus-visible` ring (`0 0 0 2px var(--gold-dim)`).
- Validation states:
  - `.is-invalid`: Red border with `.form-feedback-error` message.
  - `.is-valid`: Green border indication.

### 3.3 KPI Stat Cards (`.stat-card`)
- Built with tabular numerals (`font-variant-numeric: tabular-nums`).
- Delta indicators: `.badge-trend-up` (green with up arrow) and `.badge-trend-down` (amber/red with down arrow).
- Integrated smooth sparkline or progress bar.
- Automatic JS count-up animation triggered via `data-target="value"`.

### 3.4 Data Tables & Toolbars (`.data-table`)
- Enclosed in `.table-responsive` with custom smooth momentum scrolling (`-webkit-overflow-scrolling: touch`).
- Sticky headers (`position: sticky; top: 0; background: var(--color-surface)`).
- Status chips with circular indicator dots:
  ```html
  <span class="badge badge-success">
    <span class="status-dot"></span> Disposed
  </span>
  ```
- Hover action buttons reveal smoothly without shifting column widths.

### 3.5 Overlays: Modals & Drawers
- **Desktop**: Centered backdrop modal (`max-width: 640px` or `800px`) with blur backdrop (`backdrop-filter: blur(4px)`).
- **Mobile (< 768px)**: Automatically transforms into a bottom sheet modal with smooth `sheetSlideUp` entrance and 100% width.
- **Drawers (`.drawer`)**: Slide in from the right edge with 420px fixed width on desktop, 100% on mobile.

### 3.6 Skeletons & Empty States
- **Skeleton Loaders**: `.skeleton` element with `.skeleton-text`, `.skeleton-kpi`, `.skeleton-avatar`, `.skeleton-card`, or `.skeleton-row` containing an infinite linear shimmer animation (`skeletonShimmer`).
- **Empty States**: `.empty-state` container featuring an SVG illustration (`.empty-state-icon`), `.empty-state-title`, and `.empty-state-text` with a clear actionable call-to-action button.

---

## 4. Multi-Breakpoint Responsive Architecture

NyayaDesk is thoroughly tested and optimized across 5 standard device tiers:

```
[375px Mobile]  -->  [768px Tablet P]  -->  [1024px Tablet L]  -->  [1440px Desktop]  -->  [1920px Ultrawide]
```

### 1. 375px (Compact Mobile - iPhone SE / Galaxy S)
- Global overflow prevention: `html, body { overflow-x: hidden !important; }`.
- Sidebar hidden off-canvas (`transform: translateX(-100%)`). Toggled via topbar hamburger button.
- Sidebar opens as a sliding drawer over a blurred backdrop overlay (`#sidebar-backdrop`).
- Fixed **Mobile Bottom Nav** (`.mobile-bottom-nav`) provides 5 instant thumb-accessible tabs (Overview, Primary Action, Global Search, Alerts, Profile).
- Topbar global search collapses into an icon button.
- Modals become full-screen/bottom sheets.
- Table containers indicate horizontal scrollability with a custom gold-tinted scrollbar track.
- Touch targets strictly enforced at `min-height: 44px`.

### 2. 768px (Tablet Portrait / Large Mobile)
- KPI grids collapse to 2 columns.
- Header actions wrap cleanly without overlapping page titles.
- Modals retain comfortable margins.

### 3. 1024px (Tablet Landscape / Compact Laptops)
- Sidebar automatically transitions into an **icon-only 68px rail** (`.app-sidebar`), maximizing usable screen area for cause lists and case dockets.
- Sidebar labels hide while icons center cleanly.
- Grid layouts maintain 2 to 3 columns.

### 4. 1440px (Standard Desktop)
- Full 240px wide sidebar with expanded labels, role badge, and profile preview.
- Content area centered with a maximum width of `1560px` to maintain optimal line-lengths and data readability.
- Multi-column dashboards (e.g., Cause List + Quick Actions Docket).

### 5. 1920px (Ultrawide Displays)
- Content area constrained to `1780px` maximum width.
- Eliminates uncomfortable stretching of tables or excessively long lines of text across ultra-wide monitors.

---

## 5. Formal Judicial Print System (`@media print`)

Judicial systems require physically verifiable printed documents. NyayaDesk features a dedicated print stylesheet that removes all UI chrome (sidebar, topbar, bottom nav, buttons, toasts) and formats legal instruments with statutory precision:

### Key Print Components:
1. **`.court-print-header`**:
   - Centered High Court of Judicature letterhead.
   - SVG Ashoka Lion / Scales of Justice emblem (`.court-print-emblem`).
   - Formal jurisdiction banner (e.g., *"HIGH COURT OF JUDICATURE AT NEW DELHI / IN THE COURT OF HON'BLE SESSIONS BENCH"*).
2. **`.court-print-meta`**:
   - 2-column or 3-column judicial metadata box (CNR Number, Case Number, Filing Date, Next Hearing Date).
3. **`.court-print-signature`**:
   - Coram seal and signature block for the Presiding Judge and Court Registrar.
4. **`.court-print-qr` & `.court-print-qr-box`**:
   - Cryptographic verification section with a simulated 2D QR validation matrix, SHA-256 digital signature hash, and online verification URL (`/orders/verify/<code_id>`).

---

## 6. Theme Switching (Light & Dark Mode)

- Theme state is persisted in the browser via `localStorage.getItem('nyayadesk_theme')`.
- Applied directly on `<html>` as `data-theme="light"` or `data-theme="dark"`.
- When set to dark mode, all CSS tokens dynamically re-map with zero layout shifts or font flashes.
- Color contrast meets WCAG 2.1 AA requirements across both modes (minimum 4.5:1 for body copy and 3:1 for large headings/UI components).
