import React from 'react'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { CartProvider } from '../context/CartContext'
import { FavoritesProvider } from '../context/FavoritesContext'
import { ToastProvider } from '../context/ToastContext'

export const renderWithProviders = (ui, options = {}) => {
  const { route = '/', state, initialEntries } = options
  const entries = initialEntries || [state ? { pathname: route, state } : route]

  return render(
    <MemoryRouter initialEntries={entries}>
      <ToastProvider>
        <FavoritesProvider>
          <CartProvider>{ui}</CartProvider>
        </FavoritesProvider>
      </ToastProvider>
    </MemoryRouter>
  )
}
