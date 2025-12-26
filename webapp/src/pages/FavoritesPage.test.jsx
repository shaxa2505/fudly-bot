import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import FavoritesPage from './FavoritesPage'
import { renderWithProviders } from '../test/renderWithProviders'

vi.mock('../components/BottomNav', () => ({
  default: () => <div data-testid="bottom-nav" />,
}))

describe('FavoritesPage', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('shows empty state when there are no favorites', () => {
    renderWithProviders(<FavoritesPage />)

    expect(screen.getByText("Sevimlilar bo'sh")).toBeInTheDocument()
  })

  it('renders favorites and allows removal', async () => {
    localStorage.setItem(
      'fudly_favorites',
      JSON.stringify([
        {
          id: 11,
          title: 'Favorite Milk',
          discount_price: 4000,
          original_price: 6000,
          store_name: 'Store A',
        },
      ])
    )

    renderWithProviders(<FavoritesPage />)

    expect(await screen.findByText('Favorite Milk')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: "O'chirish" }))

    await waitFor(() => {
      expect(screen.getByText("Sevimlilar bo'sh")).toBeInTheDocument()
    })
  })
})
