// Safe storage helpers (prefer sessionStorage for sensitive data)

export const getSessionStorage = () => {
  if (typeof window === 'undefined') return null
  try {
    return window.sessionStorage
  } catch {
    return null
  }
}

export const getLocalStorage = () => {
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage
  } catch {
    return null
  }
}

export const readStorageItem = (key) => {
  const session = getSessionStorage()
  if (session) {
    try {
      const value = session.getItem(key)
      if (value != null) return value
    } catch {
      // ignore
    }
  }
  const local = getLocalStorage()
  if (local) {
    try {
      return local.getItem(key)
    } catch {
      return null
    }
  }
  return null
}

export const writeStorageItem = (key, value, { persist = false } = {}) => {
  const session = getSessionStorage()
  const local = getLocalStorage()

  if (!persist && session) {
    try {
      session.setItem(key, value)
      if (local) {
        try {
          local.removeItem(key)
        } catch {
          // ignore
        }
      }
      return 'session'
    } catch {
      // fall through
    }
  }

  if (local) {
    try {
      local.setItem(key, value)
      return 'local'
    } catch {
      // ignore
    }
  }

  if (session) {
    try {
      session.setItem(key, value)
      return 'session'
    } catch {
      // ignore
    }
  }

  return null
}

export const removeStorageItem = (key) => {
  const session = getSessionStorage()
  if (session) {
    try {
      session.removeItem(key)
    } catch {
      // ignore
    }
  }
  const local = getLocalStorage()
  if (local) {
    try {
      local.removeItem(key)
    } catch {
      // ignore
    }
  }
}

