import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { FavoritesProvider } from '../context/FavoritesContext'
import OfferCard from './OfferCard'

const mockOffer = {
  id: 1,
  title: 'Test Product',
  store_name: 'Test Store',
  discount_price: 10000,
  original_price: 15000,
  discount_percent: 33,
  photo: 'https://example.com/photo.jpg',
  quantity: 10,
  expiry_date: null,
}

const renderOfferCard = (props = {}) => {
  return render(
    <MemoryRouter>
      <FavoritesProvider>
        <OfferCard
          offer={mockOffer}
          cartQuantity={0}
          onAddToCart={vi.fn()}
          onRemoveFromCart={vi.fn()}
          {...props}
        />
      </FavoritesProvider>
    </MemoryRouter>
  )
}

describe('OfferCard', () => {
  it('renders product title', () => {
    renderOfferCard()
    expect(screen.getByText('Test Product')).toBeInTheDocument()
  })

  it('renders discount price', () => {
    renderOfferCard()
    expect(screen.getByText(/10.*000/)).toBeInTheDocument()
  })

  it('renders discount badge', () => {
    renderOfferCard()
    expect(screen.getByText('-33%')).toBeInTheDocument()
  })

  it('renders add to cart button when not in cart', () => {
    const { container } = renderOfferCard({ cartQuantity: 0 })
    const addButton = container.querySelector('.add-to-cart-inline')
    expect(addButton).toBeInTheDocument()
  })

  it('renders quantity controls when in cart', () => {
    const { container } = renderOfferCard({ cartQuantity: 2 })
    const qtyControl = container.querySelector('.quantity-control')
    expect(qtyControl).toBeInTheDocument()
    expect(screen.getByText(/2/)).toBeInTheDocument()
  })

  it('applies in-cart class when cartQuantity > 0', () => {
    const { container } = renderOfferCard({ cartQuantity: 1 })
    expect(container.querySelector('.offer-card.in-cart')).toBeInTheDocument()
  })
})
