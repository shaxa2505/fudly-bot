# Client WebApp Design Analysis

## Scope
- Focus: customer-facing webapp UI/UX (home feed, cards, filters, navigation).
- Evidence: current Home UI and shared component patterns.

## Executive Summary
- The UI lacks a clear visual hierarchy: banners, quick actions, filters, and cards compete.
- Component styling is inconsistent (radius, shadows, contrast), causing visual noise.
- Cards are information-dense without a primary focal point, slowing decision making.
- Navigation and filters take too much visual weight for their functional role.

## Critical Issues (P0)
- Competing primary actions: banners, quick actions, and product cards feel equally loud; users do not get a clear "first action."
- Offer cards overload: discount, expiry, stock, price, and CTA all vie for attention; no single dominant focal point.

## High Issues (P1)
- Visual system inconsistency: different radii, shadows, color accents, and typography weights across components.
- Secondary text contrast is too low, especially for prices, labels, and metadata; readability suffers.
- Filter state is weak: active vs inactive is not distinct enough for fast scanning.
- Overuse of effects (blur/gradients/glow) makes the UI feel heavy and noisy on mobile.

## Medium Issues (P2)
- Uneven vertical rhythm: padding and spacing vary between sections, reducing scan efficiency.
- Bottom nav consumes too much vertical space for its value.
- "Recently viewed" and "All offers" sections are stylistically inconsistent.

## Low Issues (P3)
- Mixed icon styles and stroke weights reduce visual coherence.
- Accent color is overloaded (CTA + status + highlight), blurring its meaning.

## UX Friction Points
- The first screen does not communicate a single clear path ("search" vs "browse" vs "repeat order").
- The "discount + expiry + stock + price" cluster increases cognitive load.
- The category/filter area feels like another content block rather than a control layer.

## Design Principles to Adopt
1. One dominant action per viewport.
2. Consistent component language (radius, shadow, typography).
3. Clear primary/secondary typographic scale (size and contrast).
4. Reduce decorative effects; keep functional contrast.
5. Controls (filters/nav) should be visually lighter than content.

## Target Visual System (Suggested)
- Primary color: green (brand) used for status and confirmations.
- Accent color: orange reserved for CTA and promotions.
- Text: increase secondary contrast; use fewer muted grays.
- Elevation: small, consistent shadows (no glow).
- Radius: standardize around 12-16px across cards and buttons.

## Screen-Level Recommendations

### Home
- Reduce banner height and visual dominance.
- Make search the top priority control; filters secondary.
- Limit quick actions to lower emphasis or move to secondary view.
- Simplify cards: price and CTA first; discount badge secondary.

### Offer Card
- Reduce badge count; display only discount and expiry.
- Stock indicator should be subtle (thin bar or text only).
- CTA should be a full-width, small-height button with a short label.
- Price should be the strongest text element in the card.

### Filters
- Keep filters on a single line with subtle inactive states.
- Active state should be strong (fill + contrast).
- Sorting should be secondary and compact.

### Bottom Nav
- Reduce height; remove heavy background fills.
- Active state via color + indicator line only.

## Implementation Priorities
1. Card simplification (focal point + CTA).
2. Header + search emphasis.
3. Filter and nav de-emphasis.
4. Typography and contrast normalization.
5. Component radius and shadow consistency.

## Success Metrics
- Faster first action (time to first click).
- Higher add-to-cart rate per session.
- Lower bounce from home feed.

## Open Questions
- Do we want search to be the primary entry point, or browsing categories?
- Is repeat ordering a core daily behavior (warrants top placement)?
- Are most users discount-driven or convenience-driven?
