import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import BottomNav from './BottomNav'

const renderBottomNav = (props = {}) => {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <BottomNav cartCount={0} {...props} />
    </MemoryRouter>
  )
}

describe('BottomNav', () => {
  it('renders all navigation items', () => {
    renderBottomNav()

    expect(screen.getByText('Asosiy')).toBeInTheDocument()
    expect(screen.getByText("Do'konlar")).toBeInTheDocument()
    expect(screen.getByText('Savat')).toBeInTheDocument()
    expect(screen.getByText('Buyurtmalar')).toBeInTheDocument()
    expect(screen.getByText('Profil')).toBeInTheDocument()
  })

  it('shows cart badge when cartCount > 0', () => {
    renderBottomNav({ cartCount: 5 })
    expect(screen.getByText('5')).toBeInTheDocument()
  })

  it('does not show cart badge when cartCount is 0', () => {
    const { container } = renderBottomNav({ cartCount: 0 })
    expect(container.querySelector('.nav-badge')).not.toBeInTheDocument()
  })

  it('highlights active tab based on route', () => {
    const { container } = renderBottomNav()
    const activeItem = container.querySelector('.nav-item.active')
    expect(activeItem).toBeInTheDocument()
  })
})
