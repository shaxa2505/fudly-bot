import { useState, useCallback, useRef } from 'react'
import { captureException } from '../utils/sentry'

/**
 * Universal hook for async operations with loading, error handling, and abort support
 *
 * @example
 * const { loading, error, data, execute } = useAsyncOperation()
 *
 * const loadData = async () => {
 *   const result = await execute(
 *     () => api.getOffers(),
 *     { context: 'loadOffers', successMessage: 'Loaded!' }
 *   )
 *   setOffers(result)
 * }
 */
export function useAsyncOperation() {
  const [state, setState] = useState({
    loading: false,
    error: null,
    data: null,
  })

  // Track abort controller for cleanup
  const abortControllerRef = useRef(null)

  const execute = useCallback(async (asyncFn, options = {}) => {
    const {
      context = 'operation',
      onSuccess,
      onError,
      showToast = false,
      successMessage,
      errorMessage,
    } = options

    // Cancel previous request if exists
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }

    // Create new abort controller
    const abortController = new AbortController()
    abortControllerRef.current = abortController

    setState({ loading: true, error: null, data: null })

    try {
      // Execute async function with abort signal
      const data = await asyncFn(abortController.signal)

      // Check if operation was aborted
      if (abortController.signal.aborted) {
        return null
      }

      setState({ loading: false, error: null, data })

      // Success callback
      if (onSuccess) {
        onSuccess(data)
      }

      // Show success toast
      if (showToast && successMessage && window.Telegram?.WebApp) {
        window.Telegram.WebApp.showPopup({
          message: successMessage,
          buttons: [{ type: 'ok' }],
        })
      }

      return data
    } catch (error) {
      // Ignore abort errors
      if (error.name === 'AbortError' || abortController.signal.aborted) {
        return null
      }

      const errorMsg = error.response?.data?.message || error.message || 'Unknown error'

      setState({ loading: false, error: errorMsg, data: null })

      // Log to Sentry
      captureException(error, {
        context,
        errorMessage: errorMsg,
      })

      // Error callback
      if (onError) {
        onError(error)
      }

      // Show error toast
      if (showToast && window.Telegram?.WebApp) {
        const message = errorMessage || errorMsg
        window.Telegram.WebApp.showPopup({
          message,
          buttons: [{ type: 'ok' }],
        })
      }

      throw error
    } finally {
      abortControllerRef.current = null
    }
  }, [])

  // Cleanup on unmount
  const cancel = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
  }, [])

  return {
    loading: state.loading,
    error: state.error,
    data: state.data,
    execute,
    cancel,
  }
}

/**
 * Simpler version for cases when you only need loading/error state
 */
export function useAsyncState(initialState = { loading: false, error: null }) {
  const [state, setState] = useState(initialState)

  const setLoading = useCallback((loading) => {
    setState(prev => ({ ...prev, loading }))
  }, [])

  const setError = useCallback((error) => {
    setState(prev => ({ ...prev, error, loading: false }))
    if (error) {
      captureException(new Error(error), { context: 'useAsyncState' })
    }
  }, [])

  const reset = useCallback(() => {
    setState({ loading: false, error: null })
  }, [])

  return {
    ...state,
    setLoading,
    setError,
    reset,
  }
}

export default useAsyncOperation
