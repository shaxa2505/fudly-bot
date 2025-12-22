// Форматирование цены с улучшенной читаемостью
export const formatPrice = (price, currency = "so'm") => {
  const rounded = Math.round(price)
  
  // Для больших сумм показываем сокращенно
  if (rounded >= 1000000) {
    const millions = (rounded / 1000000).toFixed(1)
    return `${millions} mln ${currency}`
  }
  
  // Для обычных сумм - с разделителями
  return `${rounded.toLocaleString('uz-UZ')} ${currency}`
}

// Компактное форматирование для маленьких пространств
export const formatPriceCompact = (price, currency = "so'm") => {
  const rounded = Math.round(price)
  
  if (rounded >= 1000000) {
    return `${(rounded / 1000000).toFixed(1)}M`
  }
  if (rounded >= 1000) {
    return `${(rounded / 1000).toFixed(0)}K`
  }
  
  return `${rounded}`
}

// Форматирование даты
export const formatDate = (dateString) => {
  const date = new Date(dateString)
  const day = date.getDate().toString().padStart(2, '0')
  const month = (date.getMonth() + 1).toString().padStart(2, '0')
  const year = date.getFullYear()
  return `${day}.${month}.${year}`
}

// Форматирование времени
export const formatTime = (dateString) => {
  const date = new Date(dateString)
  const hours = date.getHours().toString().padStart(2, '0')
  const minutes = date.getMinutes().toString().padStart(2, '0')
  return `${hours}:${minutes}`
}

// Debounce функция
export const debounce = (func, wait) => {
  let timeout
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout)
      func(...args)
    }
    clearTimeout(timeout)
    timeout = setTimeout(later, wait)
  }
}

// Throttle функция
export const throttle = (func, limit) => {
  let inThrottle
  return function(...args) {
    if (!inThrottle) {
      func.apply(this, args)
      inThrottle = true
      setTimeout(() => inThrottle = false, limit)
    }
  }
}

// Проверка на пустой объект
export const isEmpty = (obj) => {
  return Object.keys(obj).length === 0
}

// Глубокое копирование объекта
export const deepClone = (obj) => {
  return JSON.parse(JSON.stringify(obj))
}

// Генерация уникального ID
export const generateId = () => {
  return Date.now().toString(36) + Math.random().toString(36).substr(2)
}

// Валидация email
export const isValidEmail = (email) => {
  const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
  return re.test(email)
}

// Валидация телефона (узбекский формат)
export const isValidPhone = (phone) => {
  const re = /^\+998\d{9}$/
  return re.test(phone)
}

// Сокращение текста
export const truncateText = (text, maxLength) => {
  if (text.length <= maxLength) return text
  return text.substr(0, maxLength) + '...'
}

export const blurOnEnter = (event, onEnter) => {
  if (event?.key !== 'Enter' || event.shiftKey) {
    return
  }

  event.preventDefault()
  event.currentTarget?.blur?.()
  onEnter?.()
}

// Получение инициалов
export const getInitials = (name) => {
  if (!name) return '?'
  const parts = name.split(' ')
  if (parts.length >= 2) {
    return parts[0][0] + parts[1][0]
  }
  return name[0]
}

// Расчет скидки в процентах
export const calculateDiscount = (originalPrice, discountPrice) => {
  const discount = ((originalPrice - discountPrice) / originalPrice) * 100
  return Math.round(discount)
}

// Перевод единиц измерения
const UNIT_LABELS = {
  'шт': { uz: 'dona', ru: 'шт' },
  'кг': { uz: 'kg', ru: 'кг' },
  'г': { uz: 'g', ru: 'г' },
  'л': { uz: 'l', ru: 'л' },
  'мл': { uz: 'ml', ru: 'мл' },
  'упак': { uz: 'qadoq', ru: 'упак' },
  'м': { uz: 'm', ru: 'м' },
  'см': { uz: 'sm', ru: 'см' }
}

export const getUnitLabel = (unit, lang = 'uz') => {
  const normalizedUnit = (unit || 'шт').toLowerCase()
  const unitMap = UNIT_LABELS[normalizedUnit]
  if (unitMap) {
    return unitMap[lang] || unitMap['uz']
  }
  // Если единица не найдена, вернуть как есть
  return unit || 'dona'
}

// Группировка массива
export const groupBy = (array, key) => {
  return array.reduce((result, item) => {
    const group = item[key]
    if (!result[group]) {
      result[group] = []
    }
    result[group].push(item)
    return result
  }, {})
}

// Перемешивание массива
export const shuffleArray = (array) => {
  const newArray = [...array]
  for (let i = newArray.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [newArray[i], newArray[j]] = [newArray[j], newArray[i]]
  }
  return newArray
}

// Задержка (Promise)
export const sleep = (ms) => {
  return new Promise(resolve => setTimeout(resolve, ms))
}

// Retry функция
export const retry = async (fn, maxAttempts = 3, delay = 1000) => {
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      return await fn()
    } catch (error) {
      if (attempt === maxAttempts) throw error
      await sleep(delay)
    }
  }
}

// Сохранение в localStorage с проверкой
export const saveToStorage = (key, value) => {
  try {
    localStorage.setItem(key, JSON.stringify(value))
    return true
  } catch (error) {
    console.error('Error saving to localStorage:', error)
    return false
  }
}

// Чтение из localStorage с проверкой
export const getFromStorage = (key, defaultValue = null) => {
  try {
    const item = localStorage.getItem(key)
    return item ? JSON.parse(item) : defaultValue
  } catch (error) {
    console.error('Error reading from localStorage:', error)
    return defaultValue
  }
}

// Удаление из localStorage
export const removeFromStorage = (key) => {
  try {
    localStorage.removeItem(key)
    return true
  } catch (error) {
    console.error('Error removing from localStorage:', error)
    return false
  }
}
