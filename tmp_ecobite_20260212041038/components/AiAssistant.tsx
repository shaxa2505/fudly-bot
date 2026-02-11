
import React, { useState } from 'react';
import { getSmartRecipe } from '../services/geminiService';
import { DEALS, FEATURED_DEAL } from '../constants';

const AiAssistant: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [recipe, setRecipe] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const generateRecipe = async () => {
    setLoading(true);
    setIsOpen(true);
    const items = [FEATURED_DEAL.title, ...DEALS.slice(0, 2).map(d => d.title)];
    const result = await getSmartRecipe(items);
    setRecipe(result);
    setLoading(false);
  };

  return (
    <>
      {/* Floating Action Button */}
      <button 
        onClick={generateRecipe}
        className="fixed bottom-24 right-5 w-14 h-14 bg-primary text-white rounded-full shadow-lg flex items-center justify-center z-[70] hover:scale-110 active:scale-90 transition-all"
      >
        <span className="material-icons-outlined">auto_awesome</span>
      </button>

      {/* Modal / Panel */}
      {isOpen && (
        <div className="fixed inset-0 z-[100] flex items-end sm:items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
          <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl overflow-hidden animate-in slide-in-from-bottom duration-300">
            <div className="p-4 border-b border-gray-100 flex items-center justify-between bg-primary text-white">
              <div className="flex items-center gap-2">
                <span className="material-icons-outlined">auto_awesome</span>
                <h3 className="font-bold text-sm uppercase tracking-wider">AI Kitchen Assistant</h3>
              </div>
              <button onClick={() => setIsOpen(false)} className="material-icons-outlined hover:bg-white/10 rounded-full p-1">close</button>
            </div>
            
            <div className="p-6 max-h-[60vh] overflow-y-auto">
              {loading ? (
                <div className="flex flex-col items-center justify-center py-10 gap-4">
                  <div className="w-10 h-10 border-4 border-sage border-t-primary rounded-full animate-spin"></div>
                  <p className="text-sm text-charcoal/60 font-medium">Cooking up a sustainable recipe...</p>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="bg-pastel-green p-4 rounded-xl border border-primary/10">
                    <h4 className="text-xs font-bold text-primary uppercase mb-2">Based on current deals:</h4>
                    <ul className="text-[11px] text-charcoal/70 list-disc list-inside space-y-1">
                      <li>{FEATURED_DEAL.title}</li>
                      <li>{DEALS[0].title}</li>
                      <li>{DEALS[1].title}</li>
                    </ul>
                  </div>
                  <div className="prose prose-sm text-charcoal/80 leading-relaxed">
                    {recipe}
                  </div>
                </div>
              )}
            </div>
            
            <div className="p-4 border-t border-gray-100 bg-gray-50 flex gap-2">
              <button 
                onClick={generateRecipe}
                className="flex-1 py-2 bg-primary text-white rounded-xl text-xs font-bold uppercase tracking-button hover:bg-primary/90"
              >
                Regenerate
              </button>
              <button 
                onClick={() => setIsOpen(false)}
                className="flex-1 py-2 bg-white border border-gray-200 text-charcoal rounded-xl text-xs font-bold uppercase tracking-button"
              >
                Got it
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default AiAssistant;
