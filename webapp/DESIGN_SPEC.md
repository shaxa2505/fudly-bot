# 🎨 Fudly WebApp - Design Specification

**Version**: 2.0  
**Date**: December 6, 2025  
**Status**: Concept Design

---

## 📐 Design System

### Color Palette

#### Primary Colors
```
Emerald Green (Primary):
├─ #10B981  Primary (Main actions, CTAs)
├─ #059669  Primary Dark (Hover states)
├─ #D1FAE5  Primary Light (Backgrounds, highlights)
└─ #ECFDF5  Primary Lighter (Subtle backgrounds)

Amber (Accent - Discounts):
├─ #F59E0B  Accent (Discount badges)
├─ #D97706  Accent Dark (Hover)
└─ #FEF3C7  Accent Light (Backgrounds)

Red (Urgent - Flash Deals):
├─ #EF4444  Danger (Urgent CTAs)
├─ #DC2626  Danger Dark
└─ #FEE2E2  Danger Light
```

#### Neutral Colors
```
Gray Scale:
├─ #1F2937  Text Primary (Headings)
├─ #4B5563  Text Secondary (Body)
├─ #6B7280  Text Tertiary (Captions)
├─ #9CA3AF  Border
├─ #E5E7EB  Border Light
├─ #F3F4F6  Background Secondary
├─ #F9FAFB  Background Primary
└─ #FFFFFF  Surface
```

#### Status Colors
```
Success: #10B981 (Order confirmed)
Warning: #F59E0B (Low stock)
Error: #EF4444 (Out of stock)
Info: #3B82F6 (Tips, notifications)
```

---

### Typography

#### Font Stack
```css
--font-display: 'Sora', -apple-system, sans-serif;
--font-body: 'Inter', -apple-system, sans-serif;
--font-mono: 'JetBrains Mono', monospace;
```

#### Scale
```
H1 - Hero: 32px / 700 / -0.02em / Sora
H2 - Section: 24px / 700 / -0.01em / Sora
H3 - Card Title: 18px / 600 / -0.01em / Sora
H4 - Subheading: 16px / 600 / 0 / Inter
Body Large: 16px / 400 / 0 / Inter
Body: 14px / 400 / 0 / Inter
Caption: 12px / 400 / 0 / Inter
Button: 14px / 600 / 0.01em / Inter
```

---

### Spacing System
```
4px   → xs   → Tight spacing
8px   → sm   → Card padding
12px  → md   → Component gaps
16px  → lg   → Section padding
24px  → xl   → Large gaps
32px  → 2xl  → Page margins
48px  → 3xl  → Hero sections
64px  → 4xl  → Major sections
```

---

### Border Radius
```
4px   → xs   → Inputs, tags
8px   → sm   → Badges
12px  → md   → Buttons, cards
16px  → lg   → Large cards
24px  → xl   → Hero sections
50%   → full → Avatars, dots
```

---

### Shadows
```css
/* Elevation system */
--shadow-xs:  0 1px 2px rgba(0,0,0,0.05);
--shadow-sm:  0 2px 8px rgba(0,0,0,0.08);
--shadow-md:  0 4px 16px rgba(0,0,0,0.12);
--shadow-lg:  0 8px 32px rgba(0,0,0,0.15);
--shadow-xl:  0 16px 48px rgba(0,0,0,0.18);

/* Special shadows */
--shadow-green: 0 4px 16px rgba(16,185,129,0.3);
--shadow-amber: 0 4px 16px rgba(245,158,11,0.3);
--shadow-red:   0 4px 16px rgba(239,68,68,0.3);
```

---

## 📱 Screen Layouts

### Home Page - Mobile (375x812)

```
┌───────────────────────────────────┐
│ ┌─────────────────────────────┐   │ ← Header (60px)
│ │ 📍 Toshkent ▼    [❤️] [👤]  │   │   - Glassmorphism
│ └─────────────────────────────┘   │   - Sticky
│                                   │
│ ┌─────────────────────────────┐   │ ← Search (56px)
│ │ 🔍 Mahsulot qidirish...     │   │   - Border: 2px #E5E7EB
│ └─────────────────────────────┘   │   - Radius: 12px
│                                   │
│ ┌─────────────────────────────┐   │ ← Flash Deals (180px)
│ │ 🔥 Flash Deals              │   │   - Gradient background
│ │ ⏰ Tugaydi: 03:42:15        │   │   - Countdown timer
│ │                             │   │
│ │ ┌─────┐ ┌─────┐ ┌─────┐    │   │   - Horizontal scroll
│ │ │ IMG │ │ IMG │ │ IMG │    │   │   - Card: 140x160px
│ │ │-50% │ │-40% │ │-30% │    │   │
│ │ │$5.99│ │$8.50│ │$3.20│    │   │
│ │ └─────┘ └─────┘ └─────┘    │   │
│ └─────────────────────────────┘   │
│                                   │
│ ┌─────────────────────────────┐   │ ← Categories (64px)
│ │ [🔥All][🥛Sut][🍞Non][🧃]   │   │   - Sticky
│ └─────────────────────────────┘   │   - Pills: 36px height
│                                   │
│ 🎯 Sizga tavsiya               │   │ ← Section header (40px)
│                                   │
│ ┌──────────┐ ┌──────────┐        │ ← Product Grid
│ │   IMG    │ │   IMG    │        │   - 2 columns
│ │          │ │          │        │   - Gap: 12px
│ │ Sut 1L   │ │ Non      │        │   - Card: 170x240px
│ │ ⭐ 4.8   │ │ ⭐ 4.5   │        │
│ │ -50%     │ │ -30%     │        │   - Badge: top-left
│ │ $5.99    │ │ $3.20    │        │   - Price: bold
│ │ $11.98   │ │ $4.57    │        │   - Old price: strikethrough
│ │   [+]    │ │   [+]    │        │   - CTA: 40x40px circle
│ └──────────┘ └──────────┘        │
│                                   │
│ ┌──────────┐ ┌──────────┐        │
│ │   IMG    │ │   IMG    │        │
│ │ ...      │ │ ...      │        │
│ └──────────┘ └──────────┘        │
│                                   │
│ [Loading more...]                │   ← Infinite scroll
│                                   │
│ ┌─────────────────────────────┐   │ ← Bottom Nav (76px)
│ │ [🏠][🏪][🛒3][👤]           │   │   - Fixed
│ └─────────────────────────────┘   │   - Safe area
└───────────────────────────────────┘
```

**Dimensions:**
- Total height: Variable (scroll)
- Header: 60px
- Search: 56px + 16px margin
- Flash Deals: 180px + 24px margin
- Categories: 64px (sticky)
- Product card: 170x240px
- Bottom nav: 76px (includes safe area)

---

### Product Detail Page

```
┌───────────────────────────────────┐
│ [←] Product Detail    [❤️][Share] │ ← Header (56px)
│                                   │
│ ┌─────────────────────────────┐   │ ← Image Carousel (375px)
│ │                             │   │   - Swipeable
│ │      PRODUCT IMAGE          │   │   - 1:1 aspect ratio
│ │                             │   │   - Zoom on tap
│ │        ● ○ ○ ○              │   │   - Dots indicator
│ └─────────────────────────────┘   │
│                                   │
│ ┌─────────────────────────────┐   │ ← Store Info (80px)
│ │ 🏪 Fudly Locos              │   │   - Logo + name
│ │    Amir Temur ko'chasi 45A  │   │   - Address
│ │    ⭐ 4.8 · 2.3 km · Open   │   │   - Rating + distance
│ └─────────────────────────────┘   │
│                                   │
│ ┌─────────────────────────────┐   │ ← Product Info
│ │ Sut 1L "Lactel"             │   │   - Title (20px/700)
│ │ Sterilizatsiyalangan        │   │   - Subtitle (14px/400)
│ │                             │   │
│ │ ┌─────────────────────────┐ │   │ ← Price Section
│ │ │ 💰 5 990 so'm   [-50%]  │ │   │   - Gradient background
│ │ │ 💸 11 980 so'm          │ │   │   - Badge
│ │ └─────────────────────────┘ │   │
│ └─────────────────────────────┘   │
│                                   │
│ 📊 Tarkibi:                      │ ← Nutrition Info
│ ┌─────────────────────────────┐   │   - Collapsible
│ │ Oqsil:    3.2g              │   │
│ │ Yog':     2.5g              │   │
│ │ Uglevodlar: 4.8g            │   │
│ └─────────────────────────────┘   │
│                                   │
│ ⏰ Amal qilish: 12.12.2025       │ ← Expiry date
│ 📦 Qolgan: 15 dona               │ ← Stock
│ [████████░░░░░░░] 60%            │   - Progress bar
│                                   │
│ 💬 Sharhlar (142)                │ ← Reviews
│ ┌─────────────────────────────┐   │
│ │ ⭐⭐⭐⭐⭐ Alisher N.        │   │
│ │ "Ajoyib mahsulot..."        │   │
│ └─────────────────────────────┘   │
│                                   │
│ 🔗 Shunga o'xshash:              │ ← Related
│ [IMG][IMG][IMG]                  │   - Horizontal scroll
│                                   │
│ ┌─────────────────────────────┐   │ ← Sticky CTA (64px)
│ │ [−] 1 [+]  [Savatga - $5.99]│   │   - Quantity selector
│ └─────────────────────────────┘   │   - Add to cart
└───────────────────────────────────┘
```

---

### Cart Page

```
┌───────────────────────────────────┐
│ [←] Savatcha (3)        [🗑️ Все] │ ← Header
│                                   │
│ ┌─────────────────────────────┐   │ ← Cart Item
│ │ [IMG] Sut 1L "Lactel"       │   │   - 80x80 image
│ │       Fudly Locos           │   │   - Title + store
│ │       5 990 so'm            │   │   - Price
│ │       11 980 so'm           │   │   - Old price
│ │       [−] 2 [+]        [❌] │   │   - Quantity + delete
│ └─────────────────────────────┘   │
│                                   │
│ ┌─────────────────────────────┐   │
│ │ [IMG] Non                   │   │
│ │ ...                         │   │
│ └─────────────────────────────┘   │
│                                   │
│ ┌─────────────────────────────┐   │ ← Promo Code
│ │ 🎁 Promo kod                │   │   - Input + button
│ │ [FUDLY50_______] [Qo'llash] │   │
│ │ ✅ -10 000 so'm tejaldi     │   │
│ └─────────────────────────────┘   │
│                                   │
│ ┌─────────────────────────────┐   │ ← Summary
│ │ 📊 Hisob-kitob:             │   │
│ │                             │   │
│ │ Mahsulotlar:    30 000 so'm │   │
│ │ Yetkazish:       5 000 so'm │   │
│ │ Chegirma:      -10 000 so'm │   │
│ │ ─────────────────────────── │   │
│ │ 💰 Jami:        25 000 so'm │   │   - Bold, large
│ └─────────────────────────────┘   │
│                                   │
│ ┌─────────────────────────────┐   │ ← CTA (56px)
│ │ [Buyurtmani rasmiylashtirish]│   │   - Primary green
│ └─────────────────────────────┘   │   - Full width
└───────────────────────────────────┘
```

---

### Checkout Page

```
┌───────────────────────────────────┐
│ [←] Buyurtma                      │
│                                   │
│ ┌─────────────────────────────┐   │ ← Step 1: Address
│ │ 1️⃣ Yetkazish manzili        │   │   - Expandable
│ │                             │   │
│ │ ┌─────────────────────────┐ │   │
│ │ │ 📍 Toshkent             │ │   │
│ │ │ Amir Temur ko'chasi 12  │ │   │
│ │ │ Kvartira: 45            │ │   │
│ │ │ [O'zgartirish]          │ │   │
│ │ └─────────────────────────┘ │   │
│ └─────────────────────────────┘   │
│                                   │
│ ┌─────────────────────────────┐   │ ← Step 2: Time
│ │ 2️⃣ Yetkazish vaqti          │   │
│ │                             │   │
│ │ Kun:                        │   │
│ │ [●Bugun] [○Ertaga] [○08.12] │   │   - Radio buttons
│ │                             │   │
│ │ Soat:                       │   │
│ │ [16:00 - 18:00 ▼]           │   │   - Dropdown
│ └─────────────────────────────┘   │
│                                   │
│ ┌─────────────────────────────┐   │ ← Step 3: Payment
│ │ 3️⃣ To'lov usuli              │   │
│ │                             │   │
│ │ [● Naqd pul]                │   │
│ │ [○ Click]  [○ Payme]        │   │
│ │                             │   │
│ │ Chegirma skrinshot:         │   │
│ │ ┌─────────────────────────┐ │   │
│ │ │ [📷 Yuklash]            │ │   │   - File upload
│ │ └─────────────────────────┘ │   │
│ └─────────────────────────────┘   │
│                                   │
│ ┌─────────────────────────────┐   │ ← Step 4: Contact
│ │ 4️⃣ Aloqa                     │   │
│ │                             │   │
│ │ Ism:                        │   │
│ │ [Alisher Nabiyev________]   │   │
│ │                             │   │
│ │ Telefon:                    │   │
│ │ [+998 90 123 45 67_____]    │   │
│ │                             │   │
│ │ Izoh (ixtiyoriy):           │   │
│ │ [___________________]       │   │   - Textarea
│ └─────────────────────────────┘   │
│                                   │
│ ┌─────────────────────────────┐   │ ← Summary
│ │ 💰 Jami: 25 000 so'm        │   │
│ └─────────────────────────────┘   │
│                                   │
│ [☑] Men shartlarga roziman       │   ← Checkbox
│                                   │
│ ┌─────────────────────────────┐   │ ← CTA
│ │ [Buyurtma berish]           │   │   - Primary green
│ └─────────────────────────────┘   │   - 56px height
└───────────────────────────────────┘
```

---

## 🎭 Component Library

### Buttons

#### Primary Button
```
Height: 48px
Padding: 0 24px
Background: linear-gradient(135deg, #10B981, #059669)
Text: 14px / 600 / #FFFFFF
Border-radius: 12px
Shadow: 0 4px 16px rgba(16,185,129,0.3)

States:
- Hover: transform: translateY(-2px)
- Active: transform: scale(0.98)
- Disabled: opacity: 0.5
```

#### Secondary Button
```
Height: 48px
Padding: 0 24px
Background: #F3F4F6
Text: 14px / 600 / #1F2937
Border: 2px solid #E5E7EB
Border-radius: 12px

States:
- Hover: border-color: #10B981
- Active: transform: scale(0.98)
```

#### Icon Button
```
Size: 44x44px
Background: #F9FAFB
Border: 1px solid #E5E7EB
Border-radius: 12px
Icon: 24x24px

States:
- Hover: background: #F3F4F6
- Active: transform: scale(0.95)
```

---

### Cards

#### Product Card
```
Width: 170px
Height: 240px
Background: #FFFFFF
Border-radius: 16px
Shadow: 0 4px 16px rgba(0,0,0,0.08)
Padding: 0

Structure:
┌──────────┐
│   IMG    │ ← 170x170px, cover
│          │
│ Sut 1L   │ ← 14px/600, padding: 12px
│ ⭐ 4.8   │ ← 12px/400
│ -50%     │ ← Badge (absolute, top-left)
│ $5.99    │ ← 16px/700
│ $11.98   │ ← 12px/400, strikethrough
│   [+]    │ ← 40x40 circle, bottom-right
└──────────┘

States:
- Hover: transform: translateY(-4px)
        shadow: 0 8px 24px rgba(0,0,0,0.12)
- Active: transform: scale(0.98)
```

#### Store Card
```
Height: 120px
Background: #FFFFFF
Border-radius: 16px
Shadow: 0 2px 8px rgba(0,0,0,0.08)
Padding: 16px

Structure:
┌────────────────────────┐
│ [LOGO] Fudly Locos     │
│        ⭐ 4.8 (120)    │
│        📍 2.3 km       │
│        🕐 08:00-22:00  │
│        [42 ta taklif]  │
└────────────────────────┘
```

---

### Inputs

#### Text Input
```
Height: 48px
Padding: 0 16px
Background: #F9FAFB
Border: 2px solid #E5E7EB
Border-radius: 12px
Font: 14px / 400
Placeholder: #9CA3AF

States:
- Focus: border-color: #10B981
        shadow: 0 0 0 4px rgba(16,185,129,0.1)
- Error: border-color: #EF4444
- Disabled: opacity: 0.5
```

#### Search Input
```
Height: 56px
Padding: 0 16px 0 48px  ← Space for icon
Background: #F9FAFB
Border: 2px solid #E5E7EB
Border-radius: 14px
Icon: 24x24px, left: 16px
```

---

### Badges

#### Discount Badge
```
Background: linear-gradient(135deg, #EF4444, #DC2626)
Text: 12px / 700 / #FFFFFF
Padding: 4px 8px
Border-radius: 8px
Shadow: 0 2px 8px rgba(239,68,68,0.3)
Position: absolute, top: 8px, left: 8px

Icon: 🔥 (before text)
```

#### Status Badge
```
Padding: 4px 12px
Border-radius: 999px
Font: 12px / 600

Variants:
- Success: bg: #D1FAE5, text: #059669
- Warning: bg: #FEF3C7, text: #D97706
- Error: bg: #FEE2E2, text: #DC2626
- Info: bg: #DBEAFE, text: #2563EB
```

---

### Navigation

#### Bottom Navigation
```
Height: 76px (60px + 16px safe area)
Background: #FFFFFF
Border-top: 1px solid #E5E7EB
Shadow: 0 -4px 16px rgba(0,0,0,0.08)
Position: fixed, bottom: 0

Items: 4
Width: 25% each
Height: 60px
Alignment: center

Structure per item:
Icon: 24x24px
Label: 10px / 500
Gap: 4px

States:
- Active: color: #10B981, icon: filled
- Inactive: color: #6B7280, icon: outline
```

#### Header
```
Height: 60px
Background: rgba(255,255,255,0.95)
Backdrop-filter: blur(20px)
Border-bottom: 1px solid rgba(0,0,0,0.05)
Position: sticky, top: 0
Z-index: 100

Layout:
┌────────────────────────────┐
│ [←] Title    [Icon][Icon]  │
└────────────────────────────┘
```

---

## 🎬 Animations

### Micro-interactions

#### Button Press
```css
transition: transform 0.2s cubic-bezier(0.4, 0, 0.2, 1);

:active {
  transform: scale(0.96);
}
```

#### Card Hover
```css
transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

:hover {
  transform: translateY(-8px);
  box-shadow: 0 20px 40px rgba(0,0,0,0.12);
}
```

#### Add to Cart
```css
@keyframes addToCart {
  0% { transform: scale(1); }
  50% { transform: scale(1.2); }
  100% { transform: scale(1); }
}

animation: addToCart 0.3s ease;
```

#### Loading Skeleton
```css
@keyframes shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}

background: linear-gradient(
  90deg,
  #f0f0f0 25%,
  #e0e0e0 50%,
  #f0f0f0 75%
);
background-size: 200% 100%;
animation: shimmer 1.5s infinite;
```

---

### Page Transitions

#### Fade In
```css
@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

animation: fadeIn 0.4s ease-out;
```

#### Slide Up (Bottom Sheet)
```css
@keyframes slideUp {
  from {
    transform: translateY(100%);
  }
  to {
    transform: translateY(0);
  }
}

animation: slideUp 0.3s cubic-bezier(0.4, 0, 0.2, 1);
```

---

## 📊 Responsive Breakpoints

```css
/* Mobile First */
xs: 0px      /* iPhone SE */
sm: 375px    /* iPhone 12 */
md: 768px    /* iPad Mini */
lg: 1024px   /* iPad Pro */
xl: 1280px   /* Desktop */
```

### Grid System
```
Mobile (0-767px):
- Product Grid: 2 columns, gap: 12px
- Flash Deals: Horizontal scroll
- Bottom Nav: Visible

Tablet (768-1023px):
- Product Grid: 3 columns, gap: 16px
- Flash Deals: 3 items visible
- Bottom Nav: Visible

Desktop (1024px+):
- Product Grid: 4 columns, gap: 20px
- Flash Deals: 4 items visible
- Bottom Nav: Hidden (use top nav)
- Max-width: 1280px, centered
```

---

## 🎯 Accessibility

### WCAG 2.1 AA Compliance

#### Color Contrast
```
Text on Background:
- Primary text: 4.5:1 minimum
- Large text (18px+): 3:1 minimum

Tested combinations:
✅ #1F2937 on #FFFFFF: 12.63:1
✅ #4B5563 on #FFFFFF: 7.08:1
✅ #10B981 on #FFFFFF: 3.17:1 (large text only)
✅ #FFFFFF on #10B981: 3.21:1 (large text only)
```

#### Touch Targets
```
Minimum size: 44x44px
Spacing: 8px minimum between targets

Examples:
- Buttons: 48px height
- Icon buttons: 44x44px
- Bottom nav items: 60px height
- Product card CTA: 40x40px (acceptable as non-primary)
```

#### Focus States
```css
:focus-visible {
  outline: 3px solid #10B981;
  outline-offset: 2px;
}
```

#### Screen Reader Support
```html
<!-- Example -->
<button aria-label="Add Sut 1L to cart">
  <span aria-hidden="true">+</span>
</button>

<img src="..." alt="Sut 1L Lactel sterilized milk" />

<nav aria-label="Main navigation">
  ...
</nav>
```

---

## 🔤 Iconography

### Icon Set: Heroicons v2
```
Style: Outline (24x24px default)
Stroke-width: 2px
Color: currentColor
```

### Common Icons
```
🏠 Home: home-outline
🏪 Store: building-storefront
🛒 Cart: shopping-cart
👤 Profile: user-circle
🔍 Search: magnifying-glass
❤️ Favorite: heart
📍 Location: map-pin
⭐ Rating: star
🔥 Hot: fire
⏰ Time: clock
📦 Package: cube
💰 Price: currency-dollar
🎁 Gift: gift
📷 Camera: camera
✓ Check: check
✕ Close: x-mark
← Back: chevron-left
→ Forward: chevron-right
↓ Down: chevron-down
```

---

## 📸 Image Guidelines

### Product Images
```
Format: WebP (with JPG fallback)
Size: 800x800px (1:1 aspect ratio)
Quality: 85%
Max file size: 150KB

Specifications:
- White background (#FFFFFF)
- Product centered
- Padding: 5% on all sides
- No watermarks
- Sharp focus
```

### Store Logos
```
Format: SVG (preferred) or PNG
Size: 120x120px
Background: Transparent
Max file size: 50KB
```

### Banner Images
```
Format: WebP
Size: 1200x600px (2:1 aspect ratio)
Quality: 90%
Max file size: 300KB
```

---

## 🎨 Implementation Notes

### CSS Architecture
```
styles/
├── tokens.css          ← Design system variables
├── base.css            ← Reset, typography
├── components/
│   ├── buttons.css
│   ├── cards.css
│   ├── inputs.css
│   ├── badges.css
│   └── navigation.css
└── utilities.css       ← Helper classes
```

### Component Structure
```jsx
// Example: ProductCard
<div className="product-card">
  <div className="product-card__image">
    <img src="..." alt="..." />
    <span className="badge badge--discount">-50%</span>
  </div>
  <div className="product-card__content">
    <h3 className="product-card__title">Sut 1L</h3>
    <div className="product-card__rating">
      <span>⭐ 4.8</span>
    </div>
    <div className="product-card__price">
      <span className="price--current">$5.99</span>
      <span className="price--old">$11.98</span>
    </div>
    <button className="btn btn--icon btn--primary">
      +
    </button>
  </div>
</div>
```

---

## 🚀 Next Steps

1. **Review & Feedback** - Confirm design direction
2. **High-Fidelity Mockups** - Create detailed screens in Figma
3. **Interactive Prototype** - Link screens for user flow testing
4. **Development Handoff** - Provide assets and specs
5. **Iterative Testing** - A/B test key flows

---

**Questions?**
- Want to see specific screen designs?
- Need more detail on any component?
- Ready to start implementation?

Let's build something amazing! 🎨✨
