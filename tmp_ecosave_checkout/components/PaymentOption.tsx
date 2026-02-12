
import React from 'react';
import { PaymentMethodId } from '../types';

interface PaymentOptionProps {
  id: PaymentMethodId;
  label: string;
  icon: string;
  isSelected: boolean;
  onSelect: (id: PaymentMethodId) => void;
}

const PaymentOption: React.FC<PaymentOptionProps> = ({ id, label, icon, isSelected, onSelect }) => {
  return (
    <label className="relative cursor-pointer group">
      <input
        type="radio"
        name="payment"
        className="sr-only peer"
        checked={isSelected}
        onChange={() => onSelect(id)}
      />
      <div className={`
        payment-card p-4 rounded-xl border shadow-soft flex items-center justify-between transition-all duration-200 
        group-hover:border-gray-300
        ${isSelected ? 'border-primary bg-[#F0F5F1]' : 'bg-white border-gray-100'}
      `}>
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 rounded-lg bg-gray-50 flex items-center justify-center text-charcoal/80">
            <span className="material-symbols-outlined">{icon}</span>
          </div>
          <span className="text-sm font-bold text-charcoal">{label}</span>
        </div>
        <div className={`
          check-circle w-5 h-5 rounded-full border flex items-center justify-center transition-all
          ${isSelected 
            ? 'bg-primary border-primary text-white' 
            : 'border-gray-200 text-transparent'}
        `}>
          <span className="material-symbols-outlined text-[14px]">check</span>
        </div>
      </div>
    </label>
  );
};

export default PaymentOption;
