import { useState, useEffect, useCallback } from 'react'
import api from '../../api/client'
import { useCart } from '../../context/CartContext'

/**
 * Custom hook for managing checkout flow
 * Handles order creation, delivery options, payment
 *
 * @returns {Object} Checkout state and methods
 */
export function useCheckout() {
  const { cartItems, cartCount, cartTotal, clearCart } = useCart()

  // Form state
  const [phone, setPhone] = useState(() => localStorage.getItem('fudly_phone') || '')
  const [address, setAddress] = useState(() => {
    try {
      const loc = JSON.parse(localStorage.getItem('fudly_location') || '{}')
      return loc.address || ''
    } catch {
      return ''
    }
  })
  const [comment, setComment] = useState('')

  // Delivery state
  const [orderType, setOrderType] = useState('pickup') // 'pickup' | 'delivery'
  const [deliveryFee, setDeliveryFee] = useState(0)
  const [minOrderAmount, setMinOrderAmount] = useState(0)
  const [storeDeliveryEnabled, setStoreDeliveryEnabled] = useState(false)
  const [deliveryReason, setDeliveryReason] = useState('')

  // Payment state
  const [paymentProviders, setPaymentProviders] = useState([])
  const [selectedPaymentMethod, setSelectedPaymentMethod] = useState('card')
  const [paymentCard, setPaymentCard] = useState(null)
  const [paymentProof, setPaymentProof] = useState(null)
  const [paymentProofPreview, setPaymentProofPreview] = useState(null)

  // UI state
  const [orderLoading, setOrderLoading] = useState(false)
  const [showCheckout, setShowCheckout] = useState(false)
  const [checkoutStep, setCheckoutStep] = useState('details') // 'details' | 'payment' | 'upload'
  const [createdOrderId, setCreatedOrderId] = useState(null)
  const [orderResult, setOrderResult] = useState(null)

  // Load payment providers
  useEffect(() => {
    const loadProviders = async () => {
      try {
        const providers = await api.getPaymentProviders()
        setPaymentProviders(providers)
      } catch (e) {
        console.warn('Could not load payment providers:', e)
      }
    }
    loadProviders()
  }, [])

  // Check delivery availability
  useEffect(() => {
    const checkDeliveryAvailability = async () => {
      const storeIds = [...new Set(cartItems.map(item => item.offer?.store_id).filter(Boolean))]

      if (storeIds.length === 0) return

      // Multiple stores - disable delivery
      if (storeIds.length > 1) {
        setStoreDeliveryEnabled(false)
        setDeliveryFee(0)
        setMinOrderAmount(0)
        setDeliveryReason('Bir nechta do\'konlardan mahsulotlar — yetkazib berish o\'chirilgan')
        return
      }

      const storeId = storeIds[0]
      try {
        const store = await api.getStore(storeId)
        if (store?.delivery_enabled) {
          setStoreDeliveryEnabled(true)
          setDeliveryFee(store.delivery_price || 15000)
          setMinOrderAmount(store.min_order_amount || 30000)
          setDeliveryReason('')
        } else {
          setStoreDeliveryEnabled(false)
          setDeliveryFee(0)
          setMinOrderAmount(0)
          setDeliveryReason('Ushbu do\'kon yetkazib berishni qo\'llab-quvvatlamaydi')
        }
      } catch (e) {
        console.warn('Could not fetch store info:', e)
        setStoreDeliveryEnabled(false)
        setDeliveryFee(0)
        setMinOrderAmount(0)
        setDeliveryReason('Yetkazib berish ma\'lumoti olinmadi')
      }
    }

    checkDeliveryAvailability()
  }, [cartItems])

  // Calculate totals
  const subtotal = cartTotal
  const total = orderType === 'delivery' ? subtotal + deliveryFee : subtotal
  const canDelivery = subtotal >= minOrderAmount

  // Proceed to payment step
  const proceedToPayment = useCallback(async () => {
    if (!phone.trim()) {
      alert('Telefon raqamingizni kiriting')
      return false
    }
    if (orderType === 'delivery' && !address.trim()) {
      alert('Yetkazib berish manzilini kiriting')
      return false
    }

    // Pickup - skip payment
    if (orderType === 'pickup') {
      return true
    }

    // Delivery - fetch payment card
    setOrderLoading(true)
    try {
      const storeId = cartItems[0]?.offer?.store_id || 0
      const cardData = await api.getPaymentCard(storeId)
      setPaymentCard(cardData)
      setCheckoutStep('payment')
      return false // Don't place order yet
    } catch (error) {
      console.error('Error fetching payment card:', error)
      alert('To\'lov rekvizitlarini olishda xatolik')
      return false
    } finally {
      setOrderLoading(false)
    }
  }, [phone, address, orderType, cartItems])

  // Place order
  const placeOrder = useCallback(async () => {
    if (cartItems.length === 0) return null

    setOrderLoading(true)

    try {
      const userId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id || 1

      const orderData = {
        items: cartItems.map(item => ({
          offer_id: item.offer.id,
          quantity: item.quantity,
          price: item.offer.discount_price,
        })),
        delivery_type: orderType,
        phone,
        address: orderType === 'delivery' ? address : '',
        comment,
        user_id: userId,
      }

      const result = await api.createOrder(orderData)

      // Success
      setCreatedOrderId(result.order_id || result.id)
      setOrderResult({ success: true, data: result })

      // Clear cart only for pickup
      if (orderType === 'pickup') {
        clearCart()
      }

      return result
    } catch (error) {
      console.error('Error creating order:', error)
      setOrderResult({
        success: false,
        error: error.response?.data?.message || error.message || 'Buyurtma yaratilmadi',
      })
      return null
    } finally {
      setOrderLoading(false)
    }
  }, [cartItems, orderType, phone, address, comment, clearCart])

  // Upload payment proof
  const uploadPaymentProof = useCallback(async () => {
    if (!paymentProof || !createdOrderId) return false

    setOrderLoading(true)

    try {
      const formData = new FormData()
      formData.append('payment_proof', paymentProof)
      formData.append('order_id', createdOrderId)

      await api.uploadPaymentProof(formData)

      // Success - clear cart
      clearCart()
      setCheckoutStep('success')
      return true
    } catch (error) {
      console.error('Error uploading payment proof:', error)
      alert('To\'lov tasdiqlanmadi. Iltimos qayta urinib ko\'ring.')
      return false
    } finally {
      setOrderLoading(false)
    }
  }, [paymentProof, createdOrderId, clearCart])

  // Handle file selection
  const handleFileSelect = useCallback((e) => {
    const file = e.target.files?.[0]
    if (file) {
      setPaymentProof(file)
      const reader = new FileReader()
      reader.onloadend = () => {
        setPaymentProofPreview(reader.result)
      }
      reader.readAsDataURL(file)
    }
  }, [])

  return {
    // Form state
    phone,
    setPhone,
    address,
    setAddress,
    comment,
    setComment,

    // Delivery
    orderType,
    setOrderType,
    deliveryFee,
    minOrderAmount,
    storeDeliveryEnabled,
    deliveryReason,
    canDelivery,

    // Payment
    paymentProviders,
    selectedPaymentMethod,
    setSelectedPaymentMethod,
    paymentCard,
    paymentProof,
    paymentProofPreview,
    handleFileSelect,

    // Totals
    subtotal,
    total,
    itemsCount: cartCount,

    // UI state
    orderLoading,
    showCheckout,
    setShowCheckout,
    checkoutStep,
    setCheckoutStep,
    orderResult,
    setOrderResult,

    // Methods
    proceedToPayment,
    placeOrder,
    uploadPaymentProof,
  }
}

export default useCheckout
