
import React from 'react';
import { CartItem } from '../types';

interface Props {
  item: CartItem;
  onUpdateQuantity: (id: string, delta: number) => void;
  onRemove: (id: string) => void;
}

const CartItemComponent: React.FC<Props> = ({ item, onUpdateQuantity, onRemove }) => {
  return (
    <div className="flex gap-4 items-start group">
      <div className="relative w-24 h-24 flex-shrink-0 rounded-xl overflow-hidden bg-gray-100 shadow-sm border border-gray-100">
        <img 
          alt={item.name} 
          className="w-full h-full object-cover group-hover:scale-110 transition-transform duration-500" 
          src={item.image} 
        />
      </div>
      <div className="flex-1 flex flex-col h-24 justify-between py-0.5">
        <div>
          <div className="flex justify-between items-start">
            <h3 className="text-sm font-bold text-charcoal tracking-tight leading-snug pr-2">
              {item.name}
            </h3>
            <button 
              onClick={() => onRemove(item.id)}
              className="text-charcoal/30 hover:text-red-500 transition-colors"
            >
              <span className="material-symbols-outlined text-lg">close</span>
            </button>
          </div>
          <p className="text-[11px] text-charcoal/50 font-medium mt-1">{item.store}</p>
        </div>
        <div className="flex items-end justify-between">
          <div className="flex items-center gap-2">
            <span className="text-sm font-bold text-charcoal">
              {(item.price).toLocaleString()}
            </span>
            <span className="text-[11px] text-charcoal/30 line-through decoration-1">
              {(item.originalPrice).toLocaleString()}
            </span>
          </div>
          <div className="flex items-center bg-white border border-gray-200 rounded-lg h-8 shadow-sm">
            <button 
              onClick={() => onUpdateQuantity(item.id, -1)}
              className="w-8 h-full flex items-center justify-center text-charcoal/60 hover:text-charcoal active:bg-gray-50 rounded-l-lg transition-colors"
            >
              <span className="material-symbols-outlined text-sm">remove</span>
            </button>
            <span className="w-6 text-center text-xs font-bold text-charcoal">{item.quantity}</span>
            <button 
              onClick={() => onUpdateQuantity(item.id, 1)}
              className="w-8 h-full flex items-center justify-center text-charcoal/60 hover:text-charcoal active:bg-gray-50 rounded-r-lg transition-colors"
            >
              <span className="material-symbols-outlined text-sm">add</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default CartItemComponent;
