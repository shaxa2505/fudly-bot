
import React from 'react';
import { NavItem } from '../types';

interface BottomNavProps {
  activeTab: NavItem;
  onTabChange: (tab: NavItem) => void;
}

export const BottomNav: React.FC<BottomNavProps> = ({ activeTab, onTabChange }) => {
  const tabs: { id: NavItem; label: string; icon: string }[] = [
    { id: 'browse', label: 'Browse', icon: 'grid_view' },
    { id: 'saved', label: 'Saved', icon: 'favorite' },
    { id: 'cart', label: 'Cart', icon: 'shopping_cart' },
    { id: 'orders', label: 'Orders', icon: 'receipt_long' },
    { id: 'profile', label: 'Profile', icon: 'person' },
  ];

  return (
    <nav className="fixed bottom-0 left-0 right-0 bg-white/90 dark:bg-zinc-900/90 ios-blur border-t border-gray-100 dark:border-zinc-800 px-8 pt-4 pb-8 z-50">
      <div className="max-w-md mx-auto flex items-center justify-between">
        {tabs.map((tab) => {
          if (tab.id === 'cart') {
            return (
              <div key={tab.id} className="relative -top-5">
                <button 
                  onClick={() => onTabChange('cart')}
                  className={`w-14 h-14 rounded-2xl flex items-center justify-center shadow-lg shadow-primary/30 transition-all active:scale-95 ${
                    activeTab === 'cart' ? 'bg-primary' : 'bg-primary/80'
                  }`}
                >
                  <span className="material-symbols-outlined text-white text-3xl">
                    {tab.icon}
                  </span>
                </button>
              </div>
            );
          }

          const isActive = activeTab === tab.id;

          return (
            <button
              key={tab.id}
              onClick={() => onTabChange(tab.id)}
              className="flex flex-col items-center gap-1.5 group"
            >
              <span className={`material-symbols-outlined transition-colors ${
                isActive ? 'text-primary' : 'text-charcoal/40 dark:text-gray-500'
              }`}>
                {tab.icon}
              </span>
              <span className={`text-[9px] font-bold uppercase tracking-wider transition-colors ${
                isActive ? 'text-primary' : 'text-charcoal/40 dark:text-gray-500'
              }`}>
                {tab.label}
              </span>
            </button>
          );
        })}
      </div>
    </nav>
  );
};
