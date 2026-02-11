
import React from 'react';
import { View } from '../types';

interface Props {
  activeView: View;
  setActiveView: (view: View) => void;
}

const BottomNav: React.FC<Props> = ({ activeView, setActiveView }) => {
  const NavItem = ({ view, icon, label, isCenter = false }: { view: View; icon: string; label: string; isCenter?: boolean }) => {
    const isActive = activeView === view;
    
    if (isCenter) {
      return (
        <div className="relative -top-4">
          <button 
            onClick={() => setActiveView(view)}
            className={`w-14 h-14 rounded-2xl flex items-center justify-center shadow-lg transition-all active:scale-95 ${isActive ? 'bg-primary shadow-primary/20' : 'bg-gray-200 text-charcoal/40'}`}
          >
            <span className={`material-symbols-outlined text-3xl font-variation-fill-1 ${isActive ? 'text-white' : ''}`}>shopping_cart</span>
          </button>
        </div>
      );
    }

    return (
      <button 
        onClick={() => setActiveView(view)}
        className="flex flex-col items-center gap-1.5 group min-w-[50px]"
      >
        <span className={`material-symbols-outlined transition-colors ${isActive ? 'text-primary font-variation-fill-1' : 'text-charcoal/40 group-hover:text-primary'}`}>
          {icon}
        </span>
        <span className={`text-[9px] font-bold uppercase tracking-premium transition-colors ${isActive ? 'text-primary' : 'text-charcoal/40'}`}>
          {label}
        </span>
      </button>
    );
  };

  return (
    <nav className="fixed bottom-0 left-0 right-0 bg-white/90 ios-blur border-t border-gray-100 px-8 pt-4 pb-10 z-[60]">
      <div className="max-w-md mx-auto flex items-center justify-between">
        <NavItem view="browse" icon="grid_view" label="Browse" />
        <NavItem view="saved" icon="favorite" label="Saved" />
        <NavItem view="cart" icon="shopping_cart" label="Cart" isCenter />
        <NavItem view="orders" icon="receipt_long" label="Orders" />
        <NavItem view="profile" icon="person" label="Profile" />
      </div>
    </nav>
  );
};

export default BottomNav;
