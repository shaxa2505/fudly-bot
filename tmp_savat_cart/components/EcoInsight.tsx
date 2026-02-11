
import React, { useEffect, useState } from 'react';
import { CartItem } from '../types';
import { getEcoInsight } from '../services/geminiService';

interface Props {
  items: CartItem[];
}

const EcoInsight: React.FC<Props> = ({ items }) => {
  const [insight, setInsight] = useState<{ insight: string; co2SavedGrams: number } | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let isMounted = true;
    const fetchInsight = async () => {
      setLoading(true);
      const result = await getEcoInsight(items);
      if (isMounted) {
        setInsight(result);
        setLoading(false);
      }
    };

    fetchInsight();
    return () => { isMounted = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items.length]);

  if (loading) {
    return (
      <div className="mb-6 animate-pulse bg-sage/10 p-4 rounded-xl border border-sage/20">
        <div className="h-4 bg-sage/20 rounded w-3/4 mb-2"></div>
        <div className="h-3 bg-sage/20 rounded w-1/2"></div>
      </div>
    );
  }

  if (!insight) return null;

  return (
    <div className="mb-6 bg-sage/10 p-4 rounded-xl border border-sage/20 flex gap-3 items-start shadow-sm transition-all hover:bg-sage/20">
      <div className="w-8 h-8 rounded-full bg-forest-green flex items-center justify-center flex-shrink-0 mt-0.5">
        <span className="material-symbols-outlined text-white text-base font-variation-fill-1">eco</span>
      </div>
      <div>
        <p className="text-sm font-semibold text-charcoal/80 leading-snug">
          {insight.insight}
        </p>
        <p className="text-[11px] font-bold text-forest-green uppercase mt-1 tracking-premium">
          Estimated {insight.co2SavedGrams}g CO2e saved
        </p>
      </div>
    </div>
  );
};

export default EcoInsight;
