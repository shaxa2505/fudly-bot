# 🗑️ Cleanup List - Старые Файлы для Удаления

## Pages - Старые версии (удалить)
- ❌ pages/HomePage.jsx + HomePage.css → заменён на HomePageNew.jsx
- ❌ pages/ProfilePage.jsx + ProfilePage.css (есть ProfilePageNew)
- ❌ pages/CartPage.jsx + CartPage.css → пересоздадим с нуля
- ❌ pages/CategoryProductsPage.jsx + .css → старый
- ❌ pages/ExplorePage.jsx + .css → старый
- ❌ pages/FavoritesPage.jsx + .css → старый
- ❌ pages/OrderTrackingPage.jsx + .css → старый
- ❌ pages/ProductDetailPage.jsx + .css → старый
- ❌ pages/StoresPage.jsx + .css → старый
- ❌ pages/YanaPage.jsx + .css → старый
- ❌ pages/home/ (весь каталог) → старые sub-components

## Components - Дубликаты/Старые (удалить)
- ❌ HeroBanner.jsx + .css → уже удалён, но файлы остались?
- ❌ FlashDeals.jsx + .css → заменён на FlashDealsSection
- ❌ OfferCard.css → заменён на OfferCardNew.css
- ❌ BannerSlider.jsx + .css → старый
- ❌ FilterPanel.jsx + .css → старый
- ❌ StoreMap.jsx + .css → старый

## Components - Оставить ✅
- ✅ FlashDealsSection.jsx + .css (новый)
- ✅ OfferCard.jsx + OfferCardNew.css (обновлённый)
- ✅ OfferCardSkeleton.jsx + .css
- ✅ BottomNav.jsx + .css
- ✅ PullToRefresh.jsx + .css
- ✅ RecentlyViewed.jsx + .css
- ✅ ErrorBoundary.jsx + ErrorFallback
- ✅ Toast.jsx + .css
- ✅ OrderModals.jsx + .css
- ✅ OptimizedImage.jsx

## Pages - Оставить ✅
- ✅ HomePageNew.jsx + .css (новый)
- ✅ CheckoutPage.jsx + .css (обновлённый)
- ✅ ProfilePageNew.jsx + .css (новый)
- ✅ cart/ (каталог - проверим позже)

---

## Команда для удаления:

```powershell
cd webapp/src

# Удалить старые pages
Remove-Item pages/HomePage.jsx, pages/HomePage.css
Remove-Item pages/ProfilePage.jsx, pages/ProfilePage.css
Remove-Item pages/CartPage.jsx, pages/CartPage.css
Remove-Item pages/CategoryProductsPage.jsx, pages/CategoryProductsPage.css
Remove-Item pages/ExplorePage.jsx, pages/ExplorePage.css
Remove-Item pages/FavoritesPage.jsx, pages/FavoritesPage.css
Remove-Item pages/OrderTrackingPage.jsx, pages/OrderTrackingPage.css
Remove-Item pages/ProductDetailPage.jsx, pages/ProductDetailPage.css
Remove-Item pages/StoresPage.jsx, pages/StoresPage.css
Remove-Item pages/YanaPage.jsx, pages/YanaPage.css
Remove-Item -Recurse pages/home

# Удалить старые components
Remove-Item components/HeroBanner.jsx, components/HeroBanner.css -ErrorAction SilentlyContinue
Remove-Item components/FlashDeals.jsx, components/FlashDeals.css
Remove-Item components/OfferCard.css
Remove-Item components/BannerSlider.jsx, components/BannerSlider.css
Remove-Item components/FilterPanel.jsx, components/FilterPanel.css
Remove-Item components/StoreMap.jsx, components/StoreMap.css
```
