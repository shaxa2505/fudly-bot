
export interface CartItem {
  id: string;
  name: string;
  store: string;
  price: number;
  originalPrice: number;
  quantity: number;
  image: string;
}

export type View = 'browse' | 'saved' | 'cart' | 'orders' | 'profile';
