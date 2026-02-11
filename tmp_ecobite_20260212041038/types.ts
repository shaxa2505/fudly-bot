
export interface Deal {
  id: string;
  title: string;
  store: string;
  price: number;
  originalPrice: number;
  discount: string;
  imageUrl: string;
  distance: string;
  endTime: string;
  tag?: string;
  leftCount?: number;
  isFlash?: boolean;
}

export interface Category {
  id: string;
  label: string;
}

export type TabType = 'Browse' | 'Saved' | 'Cart' | 'Orders' | 'Profile';
