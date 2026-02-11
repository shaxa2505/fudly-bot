# Component Inventory (WebApp)

## Existing Reusable Components
- `BannerSlider` - `webapp/src/components/BannerSlider.jsx`
- `BottomNav` - `webapp/src/components/BottomNav.jsx`
- `Button` - `webapp/src/components/Button.jsx`
- `ErrorBoundary` / `ErrorFallback` - `webapp/src/components/ErrorBoundary.jsx`, `webapp/src/components/ErrorFallback.jsx`
- `FilterPanel` - `webapp/src/components/FilterPanel.jsx`
- `FlashDeals` - `webapp/src/components/FlashDeals.jsx`
- `HeroBanner` - `webapp/src/components/HeroBanner.jsx`
- `LocationPickerModal` - `webapp/src/components/LocationPickerModal.jsx`
- `OfferCard` / `OfferCardSkeleton` - `webapp/src/components/OfferCard.jsx`, `webapp/src/components/OfferCardSkeleton.jsx`
- `OptimizedImage` - `webapp/src/components/OptimizedImage.jsx`
- `OrderModals` - `webapp/src/components/OrderModals.jsx`
- `PageLoader` - `webapp/src/components/PageLoader.jsx`
- `PullToRefresh` - `webapp/src/components/PullToRefresh.jsx`
- `QuantityControl` - `webapp/src/components/QuantityControl.jsx`
- `RecentlyViewed` - `webapp/src/components/RecentlyViewed.jsx`
- `ScrollTopButton` - `webapp/src/components/ScrollTopButton.jsx`
- `StoreMap` - `webapp/src/components/StoreMap.jsx`
- `Toast` - `webapp/src/components/Toast.jsx`

## Gaps and Missing Components
- Order list item/card component (currently inline in `OrdersPage`).
- Status badge component for order/payment states.
- Price stack component (old price, new price, savings, discount).
- Discount badge component with consistent sizing and placement.
- Search + filter toolbar shared between Home and Category pages.
- Bulk actions bar and selection model (for high-volume workflows).
- Drawer/bottom-sheet for order details that preserves list context.
- Virtualized list/grid wrapper for large datasets.
- Standardized empty/error state component with retry.

## Recommended Standardized Component Set
1. `OrderCard` + `OrderStatusBadge`
2. `OfferCard` variants: grid + compact list
3. `PriceStack` + `DiscountBadge` + `SavingsChip`
4. `FilterBar` + `SearchBar` (shared)
5. `BulkActionsBar` + `SelectionCounter`
6. `VirtualizedList` wrapper
7. `EmptyState` / `ErrorState` with retry CTA
8. `DetailsDrawer` / `BottomSheet`
