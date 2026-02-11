
import React, { useState } from 'react';
import Header from './components/Header';
import HeroBanner from './components/HeroBanner';
import DealCard from './components/DealCard';
import ImpactWidget from './components/ImpactWidget';
import BottomNav from './components/BottomNav';
import AiAssistant from './components/AiAssistant';
import { DEALS, CATEGORIES, FEATURED_DEAL } from './constants';
import { TabType } from './types';

const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabType>('Browse');
  const [selectedCategory, setSelectedCategory] = useState('all');

  const renderContent = () => {
    if (activeTab !== 'Browse') {
      return (
        <div className="flex flex-col items-center justify-center py-20 px-10 text-center gap-4">
          <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center">
            <span className="material-symbols-outlined text-charcoal/20 text-4xl">construction</span>
          </div>
          <div>
            <h2 className="text-lg font-bold text-charcoal">Under Development</h2>
            <p className="text-sm text-charcoal/60 mt-1">The {activeTab} screen will be available soon. Check out Browse for today's deals!</p>
          </div>
          <button 
            onClick={() => setActiveTab('Browse')}
            className="px-6 py-2 bg-primary text-white rounded-xl text-sm font-bold uppercase tracking-button"
          >
            Back to Browse
          </button>
        </div>
      );
    }

    return (
      <main className="pb-32">
        <HeroBanner deal={FEATURED_DEAL} />

        <section className="px-5 py-1 overflow-x-auto flex gap-2 no-scrollbar">
          {CATEGORIES.map((cat) => (
            <button
              key={cat.id}
              onClick={() => setSelectedCategory(cat.id)}
              className={`flex-none px-4 py-2 rounded-lg text-[10px] font-extrabold uppercase tracking-button shadow-sm transition-all border ${
                selectedCategory === cat.id 
                ? 'bg-primary text-white border-primary' 
                : 'bg-white text-charcoal/80 border-gray-200 hover:border-primary/30'
              }`}
            >
              {cat.label}
            </button>
          ))}
        </section>

        <section className="px-5 pt-6 pb-2">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-black uppercase tracking-wider text-charcoal flex items-center gap-2">
              <span className="material-icons-outlined text-urgent-orange text-base">bolt</span>
              Flash Deals
            </h3>
            <div className="flex items-center gap-1 cursor-pointer group">
              <span className="text-[10px] font-bold text-primary uppercase tracking-widest group-hover:underline">Map View</span>
              <span className="material-icons-outlined text-[14px] text-primary">map</span>
            </div>
          </div>
        </section>

        <section className="px-5 grid grid-cols-2 gap-x-4 gap-y-6">
          {DEALS.map((deal) => (
            <DealCard key={deal.id} deal={deal} />
          ))}
        </section>

        <ImpactWidget />
      </main>
    );
  };

  return (
    <div className="min-h-screen bg-off-white">
      <div className="h-11 w-full bg-off-white"></div>
      <Header />
      {renderContent()}
      <BottomNav activeTab={activeTab} setActiveTab={setActiveTab} />
      <AiAssistant />
    </div>
  );
};

export default App;
