import { useState, useEffect, useCallback } from 'react'
import api from '../../api/client'

const deriveDisplayStatus = (order) => {
  const paymentStatus = order?.payment_status
  if (paymentStatus === 'awaiting_payment') return 'awaiting_payment'
  if (paymentStatus === 'awaiting_proof') return 'awaiting_proof'
  if (paymentStatus === 'proof_submitted') return 'proof_submitted'
  if (paymentStatus === 'rejected') return 'payment_rejected'
  if (paymentStatus === 'payment_rejected') return 'payment_rejected'
  return order?.order_status || order?.status || 'pending'
}

const normalizeOrders = (orders) => orders.map(order => ({
  booking_id: order.order_id || order.id,
  order_id: order.order_id || order.id,
  order_type: order.order_type,
  status: deriveDisplayStatus(order),
  order_status: order.order_status || order.status,
  payment_status: order.payment_status,
  payment_method: order.payment_method,
  created_at: order.created_at,
  delivery_address: order.delivery_address,
  total_price: order.total_price,
  items: order.items || [],
  offer_title: order.items?.[0]?.offer_title || order.items?.[0]?.title || 'Buyurtma',
  store_name: order.store_name || order.items?.[0]?.store_name || "Do'kon",
  offer_photo: api.getPhotoUrl(order.items?.[0]?.photo) || null,
  quantity: order.quantity || order.items?.reduce((sum, item) => sum + (item.quantity || 0), 0) || 1,
  booking_code: order.booking_code,
}))

const normalizeBookings = (bookings) => bookings.map(booking => ({
  ...booking,
  order_id: booking.booking_id,
  order_type: 'pickup',
  status: booking.status === 'confirmed' ? 'preparing' : (booking.status || 'pending'),
  order_status: booking.status === 'confirmed' ? 'preparing' : (booking.status || 'pending'),
  payment_status: null,
  payment_method: booking.payment_method || 'cash',
}))

const ACTIVE_STATUSES = new Set([
  'pending',
  'confirmed',
  'preparing',
  'ready',
  'delivering',
  'awaiting_payment',
  'awaiting_proof',
  'proof_submitted',
  'payment_rejected',
])

const COMPLETED_STATUSES = new Set(['completed', 'cancelled', 'rejected'])

const applyOrderFilter = (orders, orderFilter) => {
  if (orderFilter === 'active') {
    return orders.filter(order =>
      ACTIVE_STATUSES.has(order.order_status || order.status || 'pending')
    )
  }
  if (orderFilter === 'completed') {
    return orders.filter(order =>
      COMPLETED_STATUSES.has(order.order_status || order.status || '')
    )
  }
  return orders
}

export function useOrders(activeSection) {
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [orderFilter, setOrderFilter] = useState('all')

  const loadOrders = useCallback(async () => {
    setLoading(true)
    try {
      const { bookings = [], orders: rawOrders = [] } = await api.getOrders()

      const normalizedOrders = normalizeOrders(rawOrders)
      const normalizedBookings = normalizeBookings(bookings)

      const mergedOrders = [...normalizedOrders, ...normalizedBookings]
        .sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0))

    setOrders(applyOrderFilter(mergedOrders, orderFilter))
    } catch (error) {
      console.error('Error loading orders:', error)
      setOrders([])
    } finally {
      setLoading(false)
    }
  }, [orderFilter])

  useEffect(() => {
    loadOrders()

    let intervalId
    if (activeSection === 'orders') {
      intervalId = setInterval(() => {
        loadOrders()
      }, 30000)
    }

    return () => {
      if (intervalId) clearInterval(intervalId)
    }
  }, [activeSection, loadOrders])

  return {
    orders,
    loading,
    orderFilter,
    setOrderFilter,
    refreshOrders: loadOrders,
  }
}

export default useOrders
