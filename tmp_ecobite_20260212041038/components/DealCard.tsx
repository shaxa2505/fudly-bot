
import React from 'react';
import { Deal } from '../types';

interface DealCardProps {
  deal: Deal;
}

const DealCard: React.FC<DealCardProps> = ({ deal }) => {
  return (
    <div className="flex flex-col gap-2 group relative cursor-pointer">
      <div className="relative aspect-[4/5] rounded-xl overflow-hidden bg-gray-100 border border-gray-100/50 shadow-sm">
        <img 
          className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" 
          src={deal.imageUrl} 
          alt={deal.title} 
        />
        <div className={`absolute top-0 right-0 ${deal.discount.includes('SAVE') ? 'bg-urgent-orange' : 'bg-urgent-orange'} text-white text-[11px] font-black px-2 py-1 rounded-bl-xl shadow-sm z-10`}>
          {deal.discount}
        </div>
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent pt-8 pb-2 px-2">
          <div className="flex items-center justify-between">
            {deal.leftCount ? (
              <span className="text-[9px] font-bold text-white bg-red-600 px-1.5 py-0.5 rounded flex items-center gap-0.5">
                Only {deal.leftCount} left
              </span>
            ) : deal.tag ? (
              <span className={`text-[9px] font-bold text-white ${deal.tag === 'Fresh' ? 'bg-primary' : 'bg-yellow-600'} px-1.5 py-0.5 rounded flex items-center gap-0.5`}>
                {deal.tag === '1h left' && <span className="material-icons-outlined text-[9px]">schedule</span>}
                {deal.tag}
              </span>
            ) : null}
            <span className="text-[9px] font-medium text-white/90">
              {deal.distance}
            </span>
          </div>
        </div>
      </div>
      <div className="flex flex-col px-0.5">
        <div className="flex justify-between items-start">
          <span className="text-[10px] font-bold text-charcoal/60 uppercase tracking-tight truncate w-2/3">{deal.store}</span>
          <span className="text-[9px] font-bold text-discount-green bg-green-50 px-1 rounded">By {deal.endTime}</span>
        </div>
        <h4 className="text-[13px] font-bold text-charcoal truncate leading-tight mt-0.5">{deal.title}</h4>
        <div className="flex items-baseline gap-2 mt-1">
          <span className="text-base font-black text-charcoal">{deal.price.toLocaleString()}</span>
          <span className="text-[10px] text-charcoal/40 line-through decoration-red-500/50">
            {(deal.originalPrice / 1000)}k
          </span>
        </div>
      </div>
    </div>
  );
};

export default DealCard;
