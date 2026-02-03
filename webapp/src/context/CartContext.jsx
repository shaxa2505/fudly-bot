import { createContext, useContext, useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { calcItemsTotal, calcQuantity } from '../utils/orderMath';

const STORAGE_KEY = 'fudly_cart_v2';
const STORAGE_PREFIX = 'fudly_cart_user_';

const getSessionStorage = () => {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
};

const getStorageKey = () => {
  const tgUserId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id;
  if (tgUserId) {
    return `${STORAGE_PREFIX}${tgUserId}`;
  }
  const storage = getSessionStorage();
  const lastUserId =
    storage?.getItem('fudly_last_user_id') || localStorage.getItem('fudly_last_user_id');
  if (lastUserId) {
    return `${STORAGE_PREFIX}${lastUserId}`;
  }
  return STORAGE_KEY;
};

// Helper to read cart from localStorage
const getCartFromStorage = () => {
  try {
    const storageKey = getStorageKey();
    let saved = localStorage.getItem(storageKey);
    if (!saved && storageKey !== STORAGE_KEY) {
      saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        localStorage.setItem(storageKey, saved);
      }
    }
    if (!saved) return {};
    const parsed = JSON.parse(saved);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return {};
    }
    return parsed;
  } catch {
    return {};
  }
};

// Helper to save cart to localStorage
const saveCartToStorage = (cart) => {
  try {
    const storageKey = getStorageKey();
    localStorage.setItem(storageKey, JSON.stringify(cart));
  } catch (error) {
    console.error('Error saving cart to localStorage:', error);
  }
};

// Create context
const CartContext = createContext(null);

// Cart Provider component
export function CartProvider({ children }) {
  const [cart, setCart] = useState(getCartFromStorage);
  const storageKeyRef = useRef(getStorageKey());

  // Save to localStorage whenever cart changes
  useEffect(() => {
    saveCartToStorage(cart);
  }, [cart]);

  useEffect(() => {
    const syncStorageKey = () => {
      const nextKey = getStorageKey();
      if (storageKeyRef.current !== nextKey) {
        storageKeyRef.current = nextKey;
        setCart(getCartFromStorage());
      }
    };

    syncStorageKey();
    window.addEventListener('focus', syncStorageKey);
    document.addEventListener('visibilitychange', syncStorageKey);
    return () => {
      window.removeEventListener('focus', syncStorageKey);
      document.removeEventListener('visibilitychange', syncStorageKey);
    };
  }, []);

  // Add item to cart
  const addToCart = useCallback((offer) => {
    setCart((prev) => {
      const newStoreId = offer.store_id || offer.storeId || offer.store?.id
      const existingStoreId = Object.values(prev).find(item => item.offer?.store_id)?.offer?.store_id
      if (existingStoreId && newStoreId && existingStoreId !== newStoreId) {
        window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('warning')
        const message = "Savatda faqat bitta do'kondan mahsulot bo'lishi mumkin. Savatni tozalab qayta urinib ko'ring."
        if (window.Telegram?.WebApp?.showAlert) {
          window.Telegram?.WebApp?.showAlert?.(message)
        } else {
          // eslint-disable-next-line no-alert
          alert(message)
        }
        return prev
      }

      const key = String(offer.id);
      const existing = prev[key];
      const currentQty = existing?.quantity || 0;

      // Use offer's available stock as limit
      // Priority: existing.offer.stock (saved) > offer.quantity > offer.stock > 99 (fallback)
      const rawStockLimit = existing?.offer?.stock ?? offer.quantity ?? offer.stock ?? 99;
      const parsedStockLimit = Number(rawStockLimit);
      const stockLimit = Number.isFinite(parsedStockLimit) ? parsedStockLimit : 99;

      // Check if we've reached the stock limit
      if (currentQty >= stockLimit) {
        window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('warning');
        // Show toast or alert if possible
        console.warn(`Stock limit reached: ${currentQty}/${stockLimit}`);
        return prev;
      }

      const rawPhoto =
        offer.photo ||
        offer.photo_url ||
        offer.image_url ||
        offer.photoUrl ||
        offer.imageUrl ||
        offer.photo_id ||
        offer.offer_photo ||
        offer.offer_photo_url ||
        offer.image ||
        existing?.offer?.photo

      return {
        ...prev,
        [key]: {
          offer: {
            id: offer.id,
            title: offer.title || existing?.offer?.title,
            photo: rawPhoto,
            discount_price: offer.discount_price || existing?.offer?.discount_price,
            original_price: offer.original_price || existing?.offer?.original_price,
            description: offer.description || offer.short_description || existing?.offer?.description,
            store_id: offer.store_id || existing?.offer?.store_id,
            store_name: offer.store_name || existing?.offer?.store_name,
            store_address: offer.store_address || existing?.offer?.store_address,
            unit: offer.unit || existing?.offer?.unit,
            stock: stockLimit, // Save stock limit for later checks
          },
          quantity: Math.min(currentQty + 1, stockLimit),
        },
      };
    });

    // Haptic feedback
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light');
  }, []);

  // Remove one item from cart
  const removeFromCart = useCallback((offer) => {
    setCart((prev) => {
      const key = String(offer.id);
      const existing = prev[key];
      if (!existing || existing.quantity <= 1) {
        const { [key]: _, ...rest } = prev;
        return rest;
      }
      return {
        ...prev,
        [key]: { ...existing, quantity: existing.quantity - 1 },
      };
    });
  }, []);

  // Update quantity directly
  const updateQuantity = useCallback((offerId, quantity) => {
    setCart((prev) => {
      const key = String(offerId);
      const existing = prev[key];
      if (!existing) return prev;

      if (quantity <= 0) {
        const { [key]: _, ...rest } = prev;
        return rest;
      }

      // Enforce stock limit
      const rawStockLimit = existing.offer?.stock ?? 99;
      const parsedStockLimit = Number(rawStockLimit);
      const stockLimit = Number.isFinite(parsedStockLimit) ? parsedStockLimit : 99;
      const clampedQty = Math.min(quantity, stockLimit);

      if (clampedQty <= 0) {
        const { [key]: _, ...rest } = prev;
        return rest;
      }

      return {
        ...prev,
        [key]: { ...existing, quantity: clampedQty },
      };
    });
  }, []);

  const updateOfferData = useCallback((updates) => {
    if (!Array.isArray(updates) || updates.length === 0) return;
    setCart((prev) => {
      let changed = false;
      const next = { ...prev };
      updates.forEach((update) => {
        const key = String(update.offerId);
        const existing = prev[key];
        if (!existing) return;
        const patch = update.patch || {};
        next[key] = {
          ...existing,
          offer: {
            ...existing.offer,
            ...patch,
          },
        };
        changed = true;
      });
      return changed ? next : prev;
    });
  }, []);

  const replaceCart = useCallback((nextCart) => {
    if (!nextCart || typeof nextCart !== 'object' || Array.isArray(nextCart)) {
      setCart({});
      return;
    }
    const normalized = {};
    Object.values(nextCart).forEach((item) => {
      if (!item || !item.offer) return;
      const offerId = item.offer.id ?? item.offer.offer_id ?? item.offer.offerId;
      if (!offerId) return;
      const qty = Number(item.quantity ?? 0);
      if (!Number.isFinite(qty) || qty <= 0) return;
      normalized[String(offerId)] = {
        offer: item.offer,
        quantity: qty,
      };
    });
    setCart(normalized);
  }, []);

  // Remove item completely
  const removeItem = useCallback((offerId) => {
    setCart((prev) => {
      const { [String(offerId)]: _, ...rest } = prev;
      return rest;
    });
  }, []);

  // Clear entire cart
  const clearCart = useCallback(() => {
    setCart({});
  }, []);

  // Get quantity for specific offer
  const getQuantity = useCallback(
    (offerId) => {
      return cart[String(offerId)]?.quantity || 0;
    },
    [cart]
  );

  // Computed values
  const cartItems = useMemo(() => Object.values(cart), [cart]);

  const cartCount = useMemo(() => (
    calcQuantity(cartItems, item => item?.quantity ?? 0)
  ), [cartItems]);

  const cartTotal = useMemo(() => (
    calcItemsTotal(cartItems, {
      getPrice: (item) => (
        item?.offer?.discount_price ?? item?.offer?.original_price ?? 0
      ),
      getQuantity: (item) => item?.quantity ?? 0,
    })
  ), [cartItems]);

  const isEmpty = cartItems.length === 0;

  // Context value
  const value = useMemo(
    () => ({
      cart,
      cartItems,
      cartCount,
      cartTotal,
      isEmpty,
      addToCart,
      removeFromCart,
      updateQuantity,
      updateOfferData,
      replaceCart,
      removeItem,
      clearCart,
      getQuantity,
    }),
    [
      cart,
      cartItems,
      cartCount,
      cartTotal,
      isEmpty,
      addToCart,
      removeFromCart,
      updateQuantity,
      updateOfferData,
      replaceCart,
      removeItem,
      clearCart,
      getQuantity,
    ]
  );

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

// Custom hook to use cart
export function useCart() {
  const context = useContext(CartContext);
  if (!context) {
    throw new Error('useCart must be used within a CartProvider');
  }
  return context;
}

export default CartContext;
