import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ExplorePage from './ExplorePage'

vi.mock('../components/BottomNav', () => ({
  default: ({ cartCount }) => (
    <div data-testid="bottom-nav" data-count={cartCount} />
  ),
}))

describe('ExplorePage', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('filters categories by search query', () => {
    render(<ExplorePage />)

    const input = screen.getByPlaceholderText("Do'kon qidirish")
    fireEvent.change(input, { target: { value: 'meat' } })

    expect(screen.getByRole('button', { name: "Go'sht va Baliq" })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: "Mevalar va Sabzavotlar" })).not.toBeInTheDocument()
  })

  it('calls onNavigate with category payload', () => {
    const onNavigate = vi.fn()
    render(<ExplorePage onNavigate={onNavigate} />)

    fireEvent.click(screen.getByRole('button', { name: "Sut va Tuxum" }))

    expect(onNavigate).toHaveBeenCalledWith('category-products', {
      categoryId: 'dairy',
      categoryName: 'Sut va Tuxum',
    })
  })

  it('uses cart count from storage', () => {
    localStorage.setItem('fudly_cart', JSON.stringify({ '1': 2, '2': 1 }))

    render(<ExplorePage />)

    expect(screen.getByTestId('bottom-nav').dataset.count).toBe('3')
  })
})
