
import React, { useState, useMemo } from 'react';
import Header from './components/Header';
import CartItemComponent from './components/CartItem';
import OrderSummary from './components/OrderSummary';
import BottomNav from './components/BottomNav';
import EcoInsight from './components/EcoInsight';
import { CartItem, View } from './types';

const INITIAL_CART: CartItem[] = [
  {
    id: '1',
    name: 'Mixed Viennoiserie Box',
    store: 'Paul Uzbekistan',
    price: 45000,
    originalPrice: 90000,
    quantity: 1,
    image: 'https://lh3.googleusercontent.com/aida-public/AB6AXuAHMatgRdjInWiTPkP_egSNTD2A9UAra9TLyY9uFgq-tdLFwIXbUTFm3UNXMkM_0U9bPz16b5nueXBRMrwc3E5soY-aOK3Wf8CDF_3jr8XUWpx98aYC6WaNV1hw89PPQMYDfvxBPqA1JTeAaqGNYnv0hMKQrqHZYNUttZLF_mpxxQEKmDr1OMX5N8M0xqPTgPAtB5Eui4ax1qrI1zqsvWJWavQvaQBVGllx84pQ23R3F8gy7aDkazT7xDXDcc8cP4L7siZbN05fDws'
  },
  {
    id: '2',
    name: 'Margherita Classica',
    store: 'Bella Pizza',
    price: 35000,
    originalPrice: 70000,
    quantity: 1,
    image: 'https://lh3.googleusercontent.com/aida-public/AB6AXuCg6v2-eHPqdJAjw6d6NyzqbODY01sl_ihycdqFdwaL0WYPK58BmkXrRpsVRPhfCWKa16ucD0nuPxLjJ-VfiXouVSfEUqLRmjhlR_5RoSE3WsExp67a4bjNGLfzxDbjOVivG6rcyR_ZP7VZYzdfPdWlPL2Wi70GlOZjPXd2clphkxkDy5Lau-xndal5kc_223uW68kFvUKyuMqCW1a7YSxZeQGgZmV6IAvSLtQH2KJTicdMwUdusXhA6_Y8o1yAhs9qSfOutWdhJwE'
  }
];

const App: React.FC = () => {
  const [cartItems, setCartItems] = useState<CartItem[]>(INITIAL_CART);
  const [activeView, setActiveView] = useState<View>('cart');

  const updateQuantity = (id: string, delta: number) => {
    setCartItems(prev => prev.map(item => 
      item.id === id ? { ...item, quantity: Math.max(1, item.quantity + delta) } : item
    ));
  };

  const removeItem = (id: string) => {
    setCartItems(prev => prev.filter(item => item.id !== id));
  };

  const totals = useMemo(() => {
    const subtotal = cartItems.reduce((acc, item) => acc + (item.price * item.quantity), 0);
    const originalTotal = cartItems.reduce((acc, item) => acc + (item.originalPrice * item.quantity), 0);
    const rescueDiscount = originalTotal - subtotal;
    const serviceFee = 2500;
    const total = subtotal + serviceFee;
    return { subtotal, originalTotal, rescueDiscount, serviceFee, total };
  }, [cartItems]);

  return (
    <div className="flex flex-col min-h-screen max-w-lg mx-auto bg-off-white">
      <Header />

      <main className="flex-1 px-6 pt-6 pb-40">
        <section className="flex flex-col gap-8 mb-10">
          {cartItems.map(item => (
            <CartItemComponent 
              key={item.id} 
              item={item} 
              onUpdateQuantity={updateQuantity}
              onRemove={removeItem}
            />
          ))}
          {cartItems.length === 0 && (
            <div className="flex flex-col items-center justify-center py-20 text-charcoal/40">
              <span className="material-symbols-outlined text-6xl mb-4">shopping_basket</span>
              <p className="font-bold">Your cart is empty</p>
              <button 
                onClick={() => setCartItems(INITIAL_CART)}
                className="mt-4 text-primary font-bold text-sm uppercase tracking-premium"
              >
                Reset Demo
              </button>
            </div>
          )}
        </section>

        {cartItems.length > 0 && (
          <>
            <div className="h-px bg-gray-100 w-full mb-8" />
            
            <EcoInsight items={cartItems} />
            
            <OrderSummary totals={totals} />

            <div className="mt-10">
              <button className="w-full bg-forest-green text-white py-4 rounded-xl font-bold uppercase tracking-button shadow-lg shadow-primary/20 hover:shadow-primary/30 active:scale-[0.98] transition-all flex items-center justify-center gap-2 group">
                <span>Checkout</span>
                <span className="material-symbols-outlined text-sm group-hover:translate-x-1 transition-transform">arrow_forward</span>
              </button>
            </div>
          </>
        )}
      </main>

      <BottomNav activeView={activeView} setActiveView={setActiveView} />
    </div>
  );
};

export default App;
