import { describe, it, expect, beforeEach, vi } from 'vitest'

vi.mock('./auth', () => ({
  getUserId: () => 123,
}))

import { readPendingPayment, savePendingPayment, clearPendingPayment } from './pendingPayment'

describe('pendingPayment utils', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('reads and migrates base pending payment for scoped user', () => {
    const payload = {
      orderId: 11,
      createdAt: Date.now(),
      cart: { '1': { quantity: 2 } },
    }
    localStorage.setItem('fudly_pending_payment', JSON.stringify(payload))

    const result = readPendingPayment()

    expect(result.orderId).toBe(11)
    expect(localStorage.getItem('fudly_pending_payment_user_123')).not.toBeNull()
    expect(localStorage.getItem('fudly_pending_payment')).toBeNull()
  })

  it('savePendingPayment writes to user scope and clears base key', () => {
    localStorage.setItem('fudly_pending_payment', JSON.stringify({ orderId: 5 }))

    savePendingPayment({ orderId: 9, createdAt: Date.now() })

    expect(localStorage.getItem('fudly_pending_payment_user_123')).not.toBeNull()
    expect(localStorage.getItem('fudly_pending_payment')).toBeNull()
  })

  it('clearPendingPayment removes both scoped and base keys', () => {
    localStorage.setItem('fudly_pending_payment', JSON.stringify({ orderId: 1 }))
    localStorage.setItem('fudly_pending_payment_user_123', JSON.stringify({ orderId: 2 }))

    clearPendingPayment()

    expect(localStorage.getItem('fudly_pending_payment')).toBeNull()
    expect(localStorage.getItem('fudly_pending_payment_user_123')).toBeNull()
  })
})
