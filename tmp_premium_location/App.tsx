
import React, { useState, useEffect } from 'react';
import { MapBackground } from './components/MapBackground';
import { CategoryChips } from './components/CategoryChips';
import { BottomNav } from './components/BottomNav';
import { AddressDetails, NavItem, Category } from './types';

const App: React.FC = () => {
  const [address, setAddress] = useState('Chilanzar District, Tashkent');
  const [activeCategory, setActiveCategory] = useState<Category>('home');
  const [activeTab, setActiveTab] = useState<NavItem>('profile');
  const [details, setDetails] = useState<AddressDetails>({
    entrance: '1',
    floor: '4',
    apt: '24',
    note: ''
  });

  const handleInputChange = (field: keyof AddressDetails, value: string) => {
    setDetails(prev => ({ ...prev, [field]: value }));
  };

  const handleConfirm = () => {
    alert(`Location Confirmed: ${address}\nDetails: ${JSON.stringify(details)}`);
  };

  return (
    <div className="flex flex-col h-screen overflow-hidden relative bg-background-light dark:bg-background-dark font-display text-charcoal">
      {/* Map Section */}
      <MapBackground onBack={() => window.history.back()} />

      {/* Location Sheet Container */}
      <div className="absolute bottom-0 left-0 right-0 h-[60%] bg-off-white dark:bg-zinc-900 rounded-t-3xl shadow-[0_-10px_40px_-15px_rgba(0,0,0,0.15)] z-20 flex flex-col">
        {/* Sheet Handle */}
        <div className="w-full flex justify-center pt-3 pb-1">
          <div className="w-12 h-1.5 bg-gray-200 dark:bg-zinc-700 rounded-full"></div>
        </div>

        {/* Scrollable Form Content */}
        <div className="px-6 py-4 flex-1 overflow-y-auto pb-40 no-scrollbar">
          {/* Header */}
          <div className="mb-6 text-center">
            <h2 className="text-xl font-extrabold text-charcoal dark:text-white tracking-tight">Select Location</h2>
            <p className="text-xs text-charcoal/50 dark:text-gray-400 mt-1 font-medium">We'll find the best offers near you</p>
          </div>

          {/* Search Bar */}
          <div className="relative mb-6 group">
            <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
              <span className="material-icons-outlined text-primary text-xl">search</span>
            </div>
            <input 
              type="text"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              className="w-full bg-white dark:bg-zinc-800 border border-gray-200 dark:border-zinc-700 text-charcoal dark:text-white text-sm rounded-2xl py-4 pl-12 pr-10 focus:outline-none focus:border-primary/50 focus:ring-2 focus:ring-primary/10 placeholder:text-gray-400 transition-all shadow-sm"
              placeholder="Enter delivery/pickup address"
            />
            {address && (
              <button 
                onClick={() => setAddress('')}
                className="absolute inset-y-0 right-0 pr-3 flex items-center"
              >
                <span className="material-icons-outlined text-gray-400 hover:text-charcoal transition-colors text-lg">close</span>
              </button>
            )}
          </div>

          {/* Quick Categories */}
          <CategoryChips 
            activeCategory={activeCategory} 
            onSelect={setActiveCategory} 
          />

          {/* Detailed Form */}
          <div className="space-y-6 mb-6">
            <div className="flex items-center justify-between">
              <h3 className="text-[10px] font-black uppercase tracking-[0.15em] text-charcoal/40 dark:text-gray-500">Address Details</h3>
            </div>
            
            <div className="grid grid-cols-3 gap-4">
              <div className="group">
                <label className="block text-[10px] font-bold text-charcoal/60 dark:text-gray-400 mb-2 ml-1">Entrance</label>
                <input 
                  type="text" 
                  value={details.entrance}
                  onChange={(e) => handleInputChange('entrance', e.target.value)}
                  className="w-full bg-white dark:bg-zinc-800 border border-gray-200 dark:border-zinc-700 rounded-xl px-4 py-3 text-sm font-bold text-charcoal dark:text-white focus:border-primary/50 focus:ring-0 transition-colors shadow-sm"
                  placeholder="1"
                />
              </div>
              <div className="group">
                <label className="block text-[10px] font-bold text-charcoal/60 dark:text-gray-400 mb-2 ml-1">Floor</label>
                <input 
                  type="text" 
                  value={details.floor}
                  onChange={(e) => handleInputChange('floor', e.target.value)}
                  className="w-full bg-white dark:bg-zinc-800 border border-gray-200 dark:border-zinc-700 rounded-xl px-4 py-3 text-sm font-bold text-charcoal dark:text-white focus:border-primary/50 focus:ring-0 transition-colors shadow-sm"
                  placeholder="4"
                />
              </div>
              <div className="group">
                <label className="block text-[10px] font-bold text-charcoal/60 dark:text-gray-400 mb-2 ml-1">Apt/Office</label>
                <input 
                  type="text" 
                  value={details.apt}
                  onChange={(e) => handleInputChange('apt', e.target.value)}
                  className="w-full bg-white dark:bg-zinc-800 border border-gray-200 dark:border-zinc-700 rounded-xl px-4 py-3 text-sm font-bold text-charcoal dark:text-white focus:border-primary/50 focus:ring-0 transition-colors shadow-sm"
                  placeholder="24"
                />
              </div>
            </div>

            <div className="group">
              <label className="block text-[10px] font-bold text-charcoal/60 dark:text-gray-400 mb-2 ml-1">Note for courier (optional)</label>
              <textarea 
                rows={3}
                value={details.note}
                onChange={(e) => handleInputChange('note', e.target.value)}
                className="w-full bg-white dark:bg-zinc-800 border border-gray-200 dark:border-zinc-700 rounded-xl px-4 py-3 text-sm font-medium text-charcoal dark:text-white focus:border-primary/50 focus:ring-0 transition-colors resize-none shadow-sm"
                placeholder="Door code, landmarks..."
              />
            </div>
          </div>

          {/* Confirm Button */}
          <button 
            onClick={handleConfirm}
            className="w-full py-4.5 bg-primary text-white rounded-2xl shadow-xl shadow-primary/20 flex items-center justify-center gap-3 active:scale-[0.98] transition-all duration-200 mb-4"
          >
            <span className="text-xs font-black uppercase tracking-widest">Confirm Location</span>
            <span className="material-icons-outlined text-lg">arrow_forward</span>
          </button>
        </div>
      </div>

      {/* Navigation */}
      <BottomNav activeTab={activeTab} onTabChange={setActiveTab} />
    </div>
  );
};

export default App;
