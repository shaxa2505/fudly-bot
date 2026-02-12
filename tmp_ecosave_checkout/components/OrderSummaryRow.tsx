
import React from 'react';

interface OrderSummaryRowProps {
  label: string;
  value: string | number;
  isDiscount?: boolean;
  isBold?: boolean;
  icon?: string;
}

const OrderSummaryRow: React.FC<OrderSummaryRowProps> = ({ 
  label, 
  value, 
  isDiscount = false, 
  isBold = false,
  icon
}) => {
  return (
    <div className={`flex justify-between items-center text-sm ${isBold ? 'font-bold' : ''}`}>
      <div className="flex items-center gap-1.5">
        <span className={`${isDiscount ? 'text-forest-green' : 'text-charcoal/70'} ${isBold ? 'font-medium' : ''}`}>
          {label}
        </span>
        {icon && (
          <span className={`material-symbols-outlined text-[14px] ${isDiscount ? 'text-forest-green' : ''}`}>
            {icon}
          </span>
        )}
      </div>
      <span className={`${isDiscount ? 'text-forest-green' : 'text-charcoal'} ${isBold ? 'font-bold' : 'font-medium'}`}>
        {typeof value === 'number' ? value.toLocaleString() : value}
      </span>
    </div>
  );
};

export default OrderSummaryRow;
