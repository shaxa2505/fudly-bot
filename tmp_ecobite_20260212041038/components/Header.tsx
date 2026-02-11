
import React from 'react';

const Header: React.FC = () => {
  return (
    <header className="px-5 py-3 flex flex-col gap-3 sticky top-0 z-50 bg-off-white/95 ios-blur border-b border-gray-100/50">
      <div className="flex items-center justify-between relative">
        <div className="w-10"></div>
        <div className="flex flex-col items-center absolute left-1/2 -translate-x-1/2">
          <span className="text-[10px] uppercase tracking-[0.2em] text-primary/60 font-bold mb-0.5">Current Location</span>
          <div className="flex items-center gap-1 cursor-pointer group">
            <span className="text-sm font-bold text-charcoal tracking-tight">Tashkent, Chilanzar</span>
            <span className="material-icons-outlined text-sm text-primary">expand_more</span>
          </div>
        </div>
        <div className="w-9 h-9 rounded-full bg-white border border-gray-100 flex items-center justify-center shadow-sm relative">
          <span className="material-icons-outlined text-charcoal text-[20px]">notifications_none</span>
          <div className="absolute top-2 right-2.5 w-1.5 h-1.5 bg-urgent-orange rounded-full"></div>
        </div>
      </div>
      <div className="relative w-full">
        <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
          <span className="material-icons-outlined text-gray-400 text-lg">search</span>
        </div>
        <input 
          className="w-full bg-white border border-gray-200 text-charcoal text-sm rounded-xl py-2 pl-10 pr-4 focus:outline-none focus:border-primary/30 focus:ring-0 placeholder:text-gray-400 placeholder:text-xs placeholder:font-bold placeholder:uppercase placeholder:tracking-wider shadow-sm transition-all" 
          placeholder="Search for deals..." 
          type="text"
        />
      </div>
    </header>
  );
};

export default Header;
