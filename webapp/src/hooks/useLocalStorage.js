import { useState, useEffect, useCallback } from 'react'

/**
 * Hook for syncing state with localStorage
 * Automatically saves to localStorage on change and loads on mount
 * 
 * @param {string} key - localStorage key
 * @param {any} initialValue - Initial value if key doesn't exist
 * @returns {[any, Function, Function]} [value, setValue, removeValue]
 * 
 * @example
 * const [user, setUser, removeUser] = useLocalStorage('user', null)
 * 
 * setUser({ id: 1, name: 'John' })
 * // Automatically saved to localStorage
 * 
 * removeUser()
 * // Removed from localStorage
 */
export function useLocalStorage(key, initialValue) {
  // State to store our value
  const [storedValue, setStoredValue] = useState(() => {
    if (typeof window === 'undefined') {
      return initialValue
    }

    try {
      const item = window.localStorage.getItem(key)
      return item ? JSON.parse(item) : initialValue
    } catch (error) {
      console.warn(`Error loading localStorage key "${key}":`, error)
      return initialValue
    }
  })

  // Return a wrapped version of useState's setter function that
  // persists the new value to localStorage
  const setValue = useCallback((value) => {
    try {
      // Allow value to be a function so we have same API as useState
      const valueToStore = value instanceof Function ? value(storedValue) : value
      
      setStoredValue(valueToStore)
      
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(key, JSON.stringify(valueToStore))
      }
    } catch (error) {
      console.warn(`Error setting localStorage key "${key}":`, error)
    }
  }, [key, storedValue])

  // Remove from localStorage
  const removeValue = useCallback(() => {
    try {
      setStoredValue(initialValue)
      
      if (typeof window !== 'undefined') {
        window.localStorage.removeItem(key)
      }
    } catch (error) {
      console.warn(`Error removing localStorage key "${key}":`, error)
    }
  }, [key, initialValue])

  return [storedValue, setValue, removeValue]
}

/**
 * Hook for syncing multiple localStorage keys
 * Useful for related data that should be updated together
 * 
 * @param {Object} config - Object with key-value pairs for localStorage
 * @returns {Object} Object with getters, setters, and removers
 * 
 * @example
 * const storage = useLocalStorageMultiple({
 *   user: null,
 *   theme: 'light',
 *   language: 'uz'
 * })
 * 
 * storage.user.set({ id: 1 })
 * storage.theme.set('dark')
 * storage.clear() // Remove all
 */
export function useLocalStorageMultiple(config) {
  const storage = {}

  for (const [key, initialValue] of Object.entries(config)) {
    const [value, setValue, removeValue] = useLocalStorage(key, initialValue)
    
    storage[key] = {
      value,
      set: setValue,
      remove: removeValue,
    }
  }

  // Clear all keys
  storage.clear = () => {
    Object.values(storage).forEach(item => {
      if (item.remove) item.remove()
    })
  }

  return storage
}

/**
 * Hook for watching localStorage changes across tabs/windows
 * 
 * @param {string} key - localStorage key to watch
 * @param {Function} callback - Called when value changes
 * 
 * @example
 * useLocalStorageListener('cart', (newValue, oldValue) => {
 *   console.log('Cart updated:', newValue)
 *   updateUI(newValue)
 * })
 */
export function useLocalStorageListener(key, callback) {
  useEffect(() => {
    const handleStorageChange = (e) => {
      if (e.key === key && e.newValue !== e.oldValue) {
        try {
          const newValue = e.newValue ? JSON.parse(e.newValue) : null
          const oldValue = e.oldValue ? JSON.parse(e.oldValue) : null
          callback(newValue, oldValue)
        } catch (error) {
          console.warn(`Error parsing localStorage change for "${key}":`, error)
        }
      }
    }

    window.addEventListener('storage', handleStorageChange)
    
    return () => {
      window.removeEventListener('storage', handleStorageChange)
    }
  }, [key, callback])
}

export default useLocalStorage
