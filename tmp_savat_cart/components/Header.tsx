
import React from 'react';

const Header: React.FC = () => {
  return (
    <>
      <div className="h-11 w-full bg-off-white" />
      <header className="px-6 py-4 flex items-center justify-between sticky top-0 z-50 bg-off-white/90 ios-blur border-b border-gray-100/50">
        <button className="w-10 h-10 flex items-center justify-center -ml-2 text-charcoal/60 hover:text-charcoal transition-colors rounded-full active:bg-gray-100">
          <span className="material-symbols-outlined">arrow_back_ios_new</span>
        </button>
        <h1 className="text-lg font-bold tracking-tight text-charcoal">Savat</h1>
        <button className="w-10 h-10 flex items-center justify-center text-charcoal/60 hover:text-charcoal rounded-full active:bg-gray-100">
          <span className="material-symbols-outlined">more_horiz</span>
        </button>
      </header>
    </>
  );
};

export default Header;
