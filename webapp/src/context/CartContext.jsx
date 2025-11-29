import { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react';

const STORAGE_KEY = 'fudly_cart_v2';

// Helper to read cart from localStorage
const getCartFromStorage = () => {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    return saved ? JSON.parse(saved) : {};
  } catch {
    return {};
  }
};

// Helper to save cart to localStorage
const saveCartToStorage = (cart) => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(cart));
  } catch (error) {
    console.error('Error saving cart to localStorage:', error);
  }
};

// Create context
const CartContext = createContext(null);

// Cart Provider component
export function CartProvider({ children }) {
  const [cart, setCart] = useState(getCartFromStorage);

  // Save to localStorage whenever cart changes
  useEffect(() => {
    saveCartToStorage(cart);
  }, [cart]);

  // Add item to cart
  const addToCart = useCallback((offer) => {
    setCart((prev) => {
      const key = String(offer.id);
      const existing = prev[key];
      return {
        ...prev,
        [key]: {
          offer: {
            id: offer.id,
            title: offer.title,
            photo: offer.photo,
            discount_price: offer.discount_price,
            original_price: offer.original_price,
            store_id: offer.store_id,
            store_name: offer.store_name,
            store_address: offer.store_address,
          },
          quantity: (existing?.quantity || 0) + 1,
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
      return {
        ...prev,
        [key]: { ...existing, quantity },
      };
    });
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

  const cartCount = useMemo(() => {
    return cartItems.reduce((sum, item) => sum + item.quantity, 0);
  }, [cartItems]);

  const cartTotal = useMemo(() => {
    return cartItems.reduce(
      (sum, item) => sum + item.offer.discount_price * item.quantity,
      0
    );
  }, [cartItems]);

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
