
import React from 'react';
import { Deal } from '../types';

interface HeroBannerProps {
  deal: Deal;
}

const HeroBanner: React.FC<HeroBannerProps> = ({ deal }) => {
  return (
    <section className="px-5 py-4">
      <div className="relative w-full aspect-[2/1] rounded-2xl overflow-hidden shadow-soft border border-gray-100 group cursor-pointer">
        <img 
          className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-700" 
          src={deal.imageUrl} 
          alt={deal.title} 
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent"></div>
        <div className="absolute top-3 left-3 flex gap-2">
          <div className="px-2 py-1 bg-urgent-orange text-white text-[10px] font-extrabold uppercase tracking-wide rounded shadow-md">
            {deal.tag}
          </div>
        </div>
        <div className="absolute bottom-4 left-4 right-4">
          <div className="flex items-center justify-between mb-1">
            <div className="inline-block px-2 py-0.5 bg-white/20 backdrop-blur-md border border-white/30 rounded text-[9px] font-bold text-white uppercase tracking-premium">
              Featured Deal
            </div>
            <span className="text-white font-bold text-xs bg-black/40 px-2 py-0.5 rounded backdrop-blur-sm">Until {deal.endTime}</span>
          </div>
          <h2 className="text-xl font-extrabold leading-tight mb-0.5 text-white tracking-tight">{deal.title}</h2>
          <div className="flex items-end gap-2">
            <span className="text-lg text-white font-black">{deal.price.toLocaleString()} UZS</span>
            <span className="text-xs text-white/70 line-through mb-1">{(deal.originalPrice / 1000)}k</span>
            <span className="ml-auto px-2 py-1 bg-discount-green text-white text-xs font-bold rounded">{deal.discount}</span>
          </div>
        </div>
      </div>
    </section>
  );
};

export default HeroBanner;
