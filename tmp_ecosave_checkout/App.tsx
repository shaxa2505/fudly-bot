
import React, { useState } from 'react';
import PaymentOption from './components/PaymentOption';
import OrderSummaryRow from './components/OrderSummaryRow';
import { PaymentMethod, PaymentMethodId } from './types';

const PAYMENT_METHODS: PaymentMethod[] = [
  { id: 'click', label: 'Click', icon: 'credit_card' },
  { id: 'payme', label: 'Payme', icon: 'payments' },
  { id: 'cash', label: 'Cash on Pickup', icon: 'attach_money' },
];

const App: React.FC = () => {
  const [selectedPayment, setSelectedPayment] = useState<PaymentMethodId>('payme');
  const [isConfirming, setIsConfirming] = useState(false);

  const handleConfirmOrder = () => {
    setIsConfirming(true);
    // Simulate API call
    setTimeout(() => {
      alert("Order confirmed! Thank you for helping reduce food waste.");
      setIsConfirming(false);
    }, 1500);
  };

  return (
    <div className="min-h-screen bg-background-light flex flex-col">
      {/* Top Status Bar Placeholder */}
      <div className="h-11 w-full bg-off-white"></div>

      {/* Header */}
      <header className="px-6 py-4 flex items-center justify-between sticky top-0 z-50 bg-off-white/90 ios-blur border-b border-gray-100/50">
        <button className="w-10 h-10 flex items-center justify-center -ml-2 text-charcoal/60 hover:text-charcoal transition-colors">
          <span className="material-symbols-outlined">arrow_back_ios_new</span>
        </button>
        <h1 className="text-lg font-bold tracking-tight text-charcoal">Checkout</h1>
        <div className="w-10 h-10"></div>
      </header>

      {/* Main Content */}
      <main className="flex-1 pb-32 px-6 pt-8 max-w-lg mx-auto w-full">
        {/* Pickup Details */}
        <section className="mb-10">
          <h2 className="text-xl font-bold text-charcoal mb-6 tracking-tight">Pickup Details</h2>
          <div className="flex flex-col gap-4">
            <div className="bg-white p-5 rounded-xl border border-gray-100 shadow-soft flex justify-between items-start">
              <div className="flex gap-4">
                <div className="w-10 h-10 rounded-full bg-gray-50 flex items-center justify-center flex-shrink-0 text-charcoal/60">
                  <span className="material-symbols-outlined">storefront</span>
                </div>
                <div>
                  <h3 className="text-sm font-bold text-charcoal">Paul Uzbekistan</h3>
                  <p className="text-xs text-charcoal/50 mt-1 leading-relaxed">
                    Amir Temur Avenue 15,<br />Tashkent 100000
                  </p>
                </div>
              </div>
              <button className="text-[10px] font-bold uppercase tracking-premium text-forest-green border border-forest-green/20 px-3 py-1.5 rounded-full hover:bg-forest-green hover:text-white transition-colors">
                Map
              </button>
            </div>

            <div className="bg-white p-5 rounded-xl border border-gray-100 shadow-soft flex items-center gap-4">
              <div className="w-10 h-10 rounded-full bg-gray-50 flex items-center justify-center flex-shrink-0 text-charcoal/60">
                <span className="material-symbols-outlined">schedule</span>
              </div>
              <div>
                <h3 className="text-sm font-bold text-charcoal">Pickup Time</h3>
                <p className="text-xs text-forest-green font-medium mt-1">Today, 20:00 - 21:00</p>
              </div>
            </div>
          </div>
        </section>

        {/* Payment Methods */}
        <section className="mb-10">
          <h2 className="text-xl font-bold text-charcoal mb-6 tracking-tight">Payment Method</h2>
          <div className="flex flex-col gap-3">
            {PAYMENT_METHODS.map((method) => (
              <PaymentOption
                key={method.id}
                id={method.id}
                label={method.label}
                icon={method.icon}
                isSelected={selectedPayment === method.id}
                onSelect={setSelectedPayment}
              />
            ))}
          </div>
        </section>

        <div className="h-px bg-gray-100 w-full mb-8"></div>

        {/* Order Summary */}
        <section className="flex flex-col gap-4">
          <h4 className="text-xs font-bold uppercase tracking-premium text-charcoal/40 mb-2">Order Summary</h4>
          
          <div className="flex flex-col gap-2 mb-2">
            <OrderSummaryRow label="1x Mixed Viennoiserie Box" value="45,000" />
            <OrderSummaryRow label="1x Margherita Classica" value="35,000" />
          </div>

          <div className="h-px bg-gray-50 w-full my-1"></div>

          <OrderSummaryRow label="Subtotal" value="80,000 UZS" isBold />
          <OrderSummaryRow label="Service Fee" value="2,500 UZS" isBold />
          <OrderSummaryRow 
            label="Rescue Discount" 
            value="- 80,000 UZS" 
            isDiscount 
            isBold 
            icon="eco" 
          />

          <div className="mt-4 pt-4 border-t border-gray-100 flex justify-between items-center">
            <span className="text-base font-bold text-charcoal">Total</span>
            <div className="flex flex-col items-end">
              <span className="text-xl font-extrabold text-charcoal tracking-tight">82,500 UZS</span>
              <span className="text-[10px] text-charcoal/40 font-medium">Inclusive of taxes</span>
            </div>
          </div>
        </section>
      </main>

      {/* Sticky Footer */}
      <div className="fixed bottom-0 left-0 right-0 bg-white/90 ios-blur border-t border-gray-100 px-6 pt-4 pb-8 z-50">
        <button 
          onClick={handleConfirmOrder}
          disabled={isConfirming}
          className={`
            w-full bg-forest-green text-white py-4 rounded-xl font-bold uppercase tracking-button shadow-lg shadow-primary/20 
            hover:shadow-primary/30 active:scale-[0.98] transition-all flex items-center justify-center gap-2
            ${isConfirming ? 'opacity-80 cursor-not-allowed' : ''}
          `}
        >
          <span>{isConfirming ? 'Processing...' : 'Confirm Order'}</span>
          {!isConfirming && <span className="material-symbols-outlined text-sm">check_circle</span>}
        </button>
      </div>
    </div>
  );
};

export default App;
