
import React from 'react';

const ImpactWidget: React.FC = () => {
  return (
    <section className="px-5 py-6">
      <div className="bg-pastel-green rounded-2xl p-4 border border-primary/5 flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-white rounded-xl shadow-sm flex items-center justify-center flex-shrink-0">
            <span className="material-icons-outlined text-primary text-xl">eco</span>
          </div>
          <div className="flex flex-col">
            <h4 className="text-xs font-bold text-charcoal tracking-tight">Sustainable Impact</h4>
            <p className="text-[10px] text-charcoal/60 font-medium">Saved <span className="text-primary font-bold">12.4kg</span> this month.</p>
          </div>
        </div>
        <button className="px-4 py-1.5 bg-white border border-primary/10 rounded-full text-[10px] font-bold text-primary uppercase tracking-button whitespace-nowrap active:scale-95 transition-transform">
          Dashboard
        </button>
      </div>
    </section>
  );
};

export default ImpactWidget;
