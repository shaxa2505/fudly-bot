
import { GoogleGenAI, Type } from "@google/genai";
import { CartItem } from "../types";

export const getEcoInsight = async (items: CartItem[]) => {
  if (items.length === 0) return null;

  try {
    const ai = new GoogleGenAI({ apiKey: process.env.API_KEY });
    const itemsList = items.map(i => `${i.quantity}x ${i.name} from ${i.store}`).join(', ');
    
    const response = await ai.models.generateContent({
      model: "gemini-3-flash-preview",
      contents: `Calculate the estimated environmental impact of "rescuing" these food items that would have otherwise been wasted: ${itemsList}. 
      Provide a very short, encouraging 1-sentence insight (max 15 words) and a numeric CO2 savings estimate in grams.`,
      config: {
        responseMimeType: "application/json",
        responseSchema: {
          type: Type.OBJECT,
          properties: {
            insight: { type: Type.STRING },
            co2SavedGrams: { type: Type.NUMBER }
          },
          required: ["insight", "co2SavedGrams"]
        }
      }
    });

    return JSON.parse(response.text);
  } catch (error) {
    console.error("Gemini Error:", error);
    return null;
  }
};
