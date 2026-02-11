
import { GoogleGenAI } from "@google/genai";

const ai = new GoogleGenAI({ apiKey: process.env.API_KEY || '' });

export const getSmartRecipe = async (items: string[]) => {
  try {
    const response = await ai.models.generateContent({
      model: 'gemini-3-flash-preview',
      contents: `I have these food items from an anti-waste marketplace: ${items.join(', ')}. 
      Suggest a quick, delicious, and sustainable meal I can make with them. Keep it brief and encouraging.`,
      config: {
        temperature: 0.7,
        maxOutputTokens: 300,
      }
    });
    return response.text;
  } catch (error) {
    console.error("Gemini API Error:", error);
    return "Oops! I couldn't cook up a recipe right now. But those items surely make a great snack!";
  }
};
