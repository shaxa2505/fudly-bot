
export type PaymentMethodId = 'click' | 'payme' | 'cash';

export interface PaymentMethod {
  id: PaymentMethodId;
  label: string;
  icon: string;
}

export interface OrderItem {
  id: string;
  name: string;
  price: number;
  quantity: number;
}
