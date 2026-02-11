
import React from 'react';

interface MapBackgroundProps {
  onBack: () => void;
}

export const MapBackground: React.FC<MapBackgroundProps> = ({ onBack }) => {
  return (
    <div className="absolute top-0 left-0 right-0 h-[45%] z-0 relative overflow-hidden bg-gray-200">
      {/* Background Pattern / Image */}
      <div 
        className="absolute inset-0 bg-cover bg-center grayscale contrast-125 opacity-60"
        style={{ 
          backgroundImage: `url('https://picsum.photos/seed/map/1200/800')`,
          filter: 'sepia(20%) saturate(80%)'
        }}
      />
      
      {/* Back Button */}
      <button 
        onClick={onBack}
        className="absolute top-12 left-6 w-10 h-10 bg-white rounded-full shadow-lg flex items-center justify-center z-10 hover:bg-gray-50 active:scale-95 transition-all"
      >
        <span className="material-icons-outlined text-charcoal">arrow_back</span>
      </button>

      {/* Map Content Overlay */}
      <div className="w-full h-full flex items-center justify-center relative">
        <div className="relative z-10 flex flex-col items-center -mt-8">
          <div className="bg-primary/90 backdrop-blur-sm text-white text-[10px] font-bold px-3 py-1.5 rounded-lg shadow-lg mb-2 tracking-wide uppercase">
            Move map to adjust
          </div>
          <span className="material-icons-outlined text-5xl text-primary drop-shadow-2xl">location_on</span>
          <div className="w-4 h-2 bg-black/20 rounded-full blur-[2px] mt-[-4px]"></div>
        </div>
      </div>

      {/* Decorative Grid Overlap for "Map" look */}
      <div className="absolute inset-0 opacity-20 pointer-events-none" 
           style={{ backgroundImage: 'linear-gradient(#000 1px, transparent 1px), linear-gradient(90deg, #000 1px, transparent 1px)', backgroundSize: '40px 40px' }} 
      />
    </div>
  );
};
