import { useState, useCallback } from 'react'

export function useToast() {
  const [toast, setToast] = useState({
    message: '',
    type: 'info',
    isVisible: false
  })

  const showToast = useCallback((message, type = 'info', duration = 3000) => {
    setToast({ message, type, isVisible: true, duration })
  }, [])

  const hideToast = useCallback(() => {
    setToast(prev => ({ ...prev, isVisible: false }))
  }, [])

  const success = useCallback((message, duration) => showToast(message, 'success', duration), [showToast])
  const error = useCallback((message, duration) => showToast(message, 'error', duration), [showToast])
  const info = useCallback((message, duration) => showToast(message, 'info', duration), [showToast])
  const warning = useCallback((message, duration) => showToast(message, 'warning', duration), [showToast])

  return {
    toast,
    showToast,
    hideToast,
    success,
    error,
    info,
    warning
  }
}

export default useToast
