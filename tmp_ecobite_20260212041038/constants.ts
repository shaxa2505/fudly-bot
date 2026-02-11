
import { Deal, Category } from './types';

export const DEALS: Deal[] = [
  {
    id: '1',
    title: 'Mixed Viennoiserie',
    store: 'Paul Uzbekistan',
    price: 45000,
    originalPrice: 90000,
    discount: '-50%',
    imageUrl: 'https://lh3.googleusercontent.com/aida-public/AB6AXuAHMatgRdjInWiTPkP_egSNTD2A9UAra9TLyY9uFgq-tdLFwIXbUTFm3UNXMkM_0U9bPz16b5nueXBRMrwc3E5soY-aOK3Wf8CDF_3jr8XUWpx98aYC6WaNV1hw89PPQMYDfvxBPqA1JTeAaqGNYnv0hMKQrqHZYNUttZLF_mpxxQEKmDr1OMX5N8M0xqPTgPAtB5Eui4ax1qrI1zqsvWJWavQvaQBVGllx84pQ23R3F8gy7aDkazT7xDXDcc8cP4L7siZbN05fDws',
    distance: '2.4 km',
    endTime: '21:00',
    leftCount: 2,
    isFlash: true
  },
  {
    id: '2',
    title: 'Margherita Classica',
    store: 'Bella Pizza',
    price: 35000,
    originalPrice: 70000,
    discount: 'SAVE 35k',
    imageUrl: 'https://lh3.googleusercontent.com/aida-public/AB6AXuCg6v2-eHPqdJAjw6d6NyzqbODY01sl_ihycdqFdwaL0WYPK58BmkXrRpsVRPhfCWKa16ucD0nuPxLjJ-VfiXouVSfEUqLRmjhlR_5RoSE3WsExp67a4bjNGLfzxDbjOVivG6rcyR_ZP7VZYzdfPdWlPL2Wi70GlOZjPXd2clphkxkDy5Lau-xndal5kc_223uW68kFvUKyuMqCW1a7YSxZeQGgZmV6IAvSLtQH2KJTicdMwUdusXhA6_Y8o1yAhs9qSfOutWdhJwE',
    distance: '0.8 km',
    endTime: '22:00',
    tag: '1h left',
    isFlash: true
  },
  {
    id: '3',
    title: 'Seasonal Fruit Box',
    store: 'Korzinka.uz',
    price: 22000,
    originalPrice: 45000,
    discount: '-51%',
    imageUrl: 'https://lh3.googleusercontent.com/aida-public/AB6AXuAdQJF-ZZPrcq9S2Qd6aQ7KsEysteO3vZm1RXRv_QYkkFATc0-J7YRkjAVsP_TBkmaC-HZV3_f-SLAA2u3KRlxaWk_ZuUGIbAsJZ5VK-eHY-ynhQpEHngBLkEW0e6ai9OexYDgCMyFOs8IjnCCeZ0clISRqzG08xfMnQAUcd0bL-b45LFOgtmtMBOkp7YRRbJYchAgTPzG5hNlIXH5R7MEkVs5--Hmd3X8mVcmpEIk64iI8dAzbk63xNZt0KKrmPV4rePUANa7-Kys',
    distance: '1.2 km',
    endTime: '23:00',
    tag: 'Fresh',
    isFlash: true
  },
  {
    id: '4',
    title: 'Gourmet Dessert Mix',
    store: 'Safia Cafe',
    price: 58000,
    originalPrice: 115000,
    discount: '-50%',
    imageUrl: 'https://lh3.googleusercontent.com/aida-public/AB6AXuCIiKMJFCeirU8R3dSeHWqINYaqmOle3YhUdjpAZJBCWqNtPchCJUQokxfIHImZk4YKWlSRjhKeKP0to3AErXQpJmAo2ldjzLGDTKT6FMt9x8gi5Qj2RtFWzziq6oksFU0p1nKdbT0qD00iCUxzmDwZ2Hqc4ZPmUYeVwgC2S1tDJiTUNJXm3FDeq-1jeU2hjd3SDpaaEek0nbgpch6H_WSJLfKIiMdnMx1lGcCb0DX6uYxIVqEC71YsSX1pS39GAgBlZZFH-lQFpY8',
    distance: '3.5 km',
    endTime: '20:30',
    leftCount: 1,
    isFlash: true
  }
];

export const CATEGORIES: Category[] = [
  { id: 'all', label: 'All Deals' },
  { id: 'bakeries', label: 'Bakeries' },
  { id: 'markets', label: 'Markets' },
  { id: 'cafes', label: 'Cafes' }
];

export const FEATURED_DEAL: Deal = {
  id: 'featured',
  title: 'Artisan Sourdough Bundle',
  store: 'Bread & Butter',
  price: 15000,
  originalPrice: 30000,
  discount: '-50% OFF',
  imageUrl: 'https://lh3.googleusercontent.com/aida-public/AB6AXuBJ2-LfKv-EUjOdjmzho5nNc-lQ8Kv0Ao_NKn6DyxpAgqM_BItKSV6DbLtu8C67xcAu-YB48ZPoaYzGUxiBfVcqKmyCqKRB55NJv_XA_x0_0nsRRvJdXpddRmmmraCYVI_3T-6KaobOMbHldWC0Y3UYy-u1WMtO_2eHkl8arGb2cCIwzaJXAgSmM3fghyGVtJnMngEgI6i7IffDZfJe-g08pM-Ui8SvOCBT5c3s3Fh5LZeb_RqsIYZ2kxOjbIFDvfeOG5B-qAo4i5w',
  distance: '0.5 km',
  endTime: '21:00',
  tag: 'Closing Soon'
};
