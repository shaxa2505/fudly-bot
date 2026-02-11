
import React from 'react';

interface Props {
  totals: {
    subtotal: number;
    serviceFee: number;
    rescueDiscount: number;
    total: number;
  };
}

const OrderSummary: React.FC<Props> = ({ totals }) => {
  return (
    <section className="flex flex-col gap-4 mt-8">
      <h4 className="text-xs font-bold uppercase tracking-premium text-charcoal/40 mb-2">Order Summary</h4>
      
      <div className="flex justify-between items-center text-sm">
        <span className="text-charcoal/70 font-medium">Subtotal</span>
        <span className="text-charcoal font-bold">{totals.subtotal.toLocaleString()} UZS</span>
      </div>
      
      <div className="flex justify-between items-center text-sm">
        <span className="text-charcoal/70 font-medium">Service Fee</span>
        <span className="text-charcoal font-bold">{totals.serviceFee.toLocaleString()} UZS</span>
      </div>
      
      <div className="flex justify-between items-center text-sm">
        <div className="flex items-center gap-1.5">
          <span className="text-forest-green font-medium">Rescue Discount</span>
          <span className="material-symbols-outlined text-forest-green text-[14px] font-variation-fill-1">eco</span>
        </div>
        <span className="text-forest-green font-bold">- {totals.rescueDiscount.toLocaleString()} UZS</span>
      </div>

      <div className="mt-4 pt-4 border-t border-gray-100 flex justify-between items-center">
        <span className="text-base font-bold text-charcoal">Total</span>
        <div className="flex flex-col items-end">
          <span className="text-xl font-extrabold text-charcoal tracking-tight">
            {totals.total.toLocaleString()} UZS
          </span>
          <span className="text-[10px] text-charcoal/40 font-medium">Inclusive of taxes</span>
        </div>
      </div>
    </section>
  );
};

export default OrderSummary;
