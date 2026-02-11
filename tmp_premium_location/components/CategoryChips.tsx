
import React from 'react';
import { Category } from '../types';

interface CategoryChipsProps {
  activeCategory: Category;
  onSelect: (category: Category) => void;
}

export const CategoryChips: React.FC<CategoryChipsProps> = ({ activeCategory, onSelect }) => {
  const categories: { id: Category; label: string; icon: string }[] = [
    { id: 'home', label: 'Home', icon: 'home' },
    { id: 'work', label: 'Work', icon: 'work' },
    { id: 'yunusabad', label: 'Yunusabad', icon: 'history' },
  ];

  return (
    <div className="flex gap-3 mb-8 overflow-x-auto pb-2 no-scrollbar">
      {categories.map((cat) => (
        <button
          key={cat.id}
          onClick={() => onSelect(cat.id)}
          className={`flex items-center gap-2 px-5 py-2.5 rounded-xl border shadow-sm transition-all flex-shrink-0 group ${
            activeCategory === cat.id
              ? 'bg-primary border-primary'
              : 'bg-white dark:bg-zinc-800 border-gray-100 dark:border-zinc-700'
          }`}
        >
          <span className={`material-icons-outlined text-lg ${
            activeCategory === cat.id ? 'text-white' : 'text-primary'
          }`}>
            {cat.icon}
          </span>
          <span className={`text-xs font-bold tracking-wide ${
            activeCategory === cat.id ? 'text-white' : 'text-charcoal dark:text-white'
          }`}>
            {cat.label}
          </span>
        </button>
      ))}
    </div>
  );
};
