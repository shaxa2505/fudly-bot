
import React from 'react';
import { TabType } from '../types';

interface BottomNavProps {
  activeTab: TabType;
  setActiveTab: (tab: TabType) => void;
}

const BottomNav: React.FC<BottomNavProps> = ({ activeTab, setActiveTab }) => {
  const tabs: { label: TabType; icon: string }[] = [
    { label: 'Browse', icon: 'grid_view' },
    { label: 'Saved', icon: 'favorite' },
    { label: 'Cart', icon: 'shopping_cart' },
    { label: 'Orders', icon: 'receipt_long' },
    { label: 'Profile', icon: 'person' },
  ];

  return (
    <nav className="fixed bottom-0 left-0 right-0 bg-white/95 ios-blur border-t border-gray-100 z-[60] pb-safe shadow-[0_-1px_10px_rgba(0,0,0,0.02)]">
      <div className="flex items-center justify-around w-full py-2 pb-5 px-2">
        {tabs.map((tab) => (
          <button
            key={tab.label}
            onClick={() => setActiveTab(tab.label)}
            className={`flex flex-col items-center justify-center gap-1 min-w-[60px] transition-all ${
              activeTab === tab.label ? 'text-primary' : 'text-charcoal/40'
            }`}
          >
            <span 
              className={`material-symbols-outlined text-[24px] ${
                activeTab === tab.label ? 'font-variation-fill-1' : ''
              }`}
            >
              {tab.icon}
            </span>
            <span className={`text-[10px] tracking-tight ${activeTab === tab.label ? 'font-bold' : 'font-medium'}`}>
              {tab.label}
            </span>
          </button>
        ))}
      </div>
    </nav>
  );
};

export default BottomNav;
