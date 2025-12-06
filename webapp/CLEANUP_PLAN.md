# Fudly WebApp - Cleanup Plan

## 🗑️ Файлы для Удаления (Старый Код)

### 1. Старые Design System файлы
- [ ] `src/styles/design-tokens.css` → заменён на `tokens.css`
- [ ] `src/styles/shared-components.css` → заменён на `components/`
- [ ] `src/styles/accessibility.css` → интегрировано в `animations-enhanced.css`
- [ ] `src/styles/animations.css` → заменён на `animations-enhanced.css`

### 2. Компоненты для Удаления
- [ ] `src/components/HeroBanner.jsx` + `.css` → не используется после рефакторинга
- [ ] `src/pages/home/HeroSection.jsx` → удалён из HomePage

### 3. CSS для Очистки в HomePage.css
- [ ] `.hero-*` классы (lines 335-430)
- [ ] `.category-pill` классы (lines 77-143) → используем `.chip`
- [ ] `.filter-chip` классы (lines 859-910) → используем `.chip`
- [ ] Старые rgba(83, 177, 117, ...) цвета → используем `var(--color-primary)`

### 4. CSS для Очистки в других страницах
- [ ] `YanaPage.css` - `.filter-chip` классы
- [ ] `StoresPage.css` - старые rgba цвета
- [ ] `ErrorFallback.css` - старые rgba цвета

### 5. Обновить импорты в App.jsx
```jsx
// Удалить:
import './styles/animations.css'

// Уже есть:
import './styles/main.css' // (содержит animations-enhanced.css)
```

---

## ✅ Что Оставляем (Новый Design System v2.0)

### Core Files
- ✅ `styles/tokens.css` - CSS переменные
- ✅ `styles/main.css` - главный файл с импортами
- ✅ `styles/animations-enhanced.css` - система анимаций
- ✅ `styles/components/` - 5 модулей (buttons, inputs, badges, cards, navigation)

### Components
- ✅ `FlashDealsSection.jsx` + `.css`
- ✅ `OfferCard.jsx` + `OfferCardNew.css`
- ✅ `CartPage.jsx` + `.css`
- ✅ `CheckoutPage.jsx` + `.css`

### Pages
- ✅ `HomePage.jsx` (без HeroSection)
- ✅ `CategoriesSection.jsx` (обновлён на `.chip`)
- ✅ `FiltersPanel.jsx` (обновлён на `.chip`)

---

## 📝 План Действий

### Шаг 1: Удалить старые design system файлы
```powershell
cd webapp/src/styles
Remove-Item design-tokens.css, shared-components.css, accessibility.css, animations.css
```

### Шаг 2: Удалить HeroBanner компонент
```powershell
cd webapp/src/components
Remove-Item HeroBanner.jsx, HeroBanner.css
cd ../pages/home
Remove-Item HeroSection.jsx
```

### Шаг 3: Очистить HomePage.css
- Удалить `.hero-*` блок (lines 335-430)
- Удалить `.category-pill` блок (lines 77-143)
- Удалить `.filter-chip` блок (lines 859-910)

### Шаг 4: Обновить App.jsx
- Удалить импорт `animations.css`

### Шаг 5: Очистить другие страницы
- YanaPage.css - удалить `.filter-chip`
- Заменить все `rgba(83, 177, 117, ...)` на `var(--color-primary)` или `var(--shadow-green)`

---

## 🎯 Результат

После очистки останется только:
- **tokens.css** (280 lines) - переменные
- **main.css** (487 lines) - импорты + утилиты
- **animations-enhanced.css** (382 lines) - анимации
- **components/** (5 файлов, ~1640 lines) - компоненты
- Чистый код без legacy остатков
