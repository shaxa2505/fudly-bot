/**
 * Pull-to-Refresh Hook
 * Обрабатывает жест тяги вниз для обновления контента
 */

import { useState, useEffect, useCallback, useRef } from 'react'

export function usePullToRefresh(onRefresh, options = {}) {
  const {
    threshold = 80,
    resistance = 2.5,
    maxPull = 120,
    refreshTimeout = 2000
  } = options

  const [isPulling, setIsPulling] = useState(false)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [pullDistance, setPullDistance] = useState(0)

  const startY = useRef(0)
  const startX = useRef(0)
  const currentY = useRef(0)
  const containerRef = useRef(null)
  const isTracking = useRef(false)

<<<<<<< HEAD
  const getScrollTop = useCallback(() => {
    const container = containerRef.current
    if (container && container !== document && container !== document.body && container !== document.documentElement) {
      return container.scrollTop
    }
    const scrollElement = document.scrollingElement || document.documentElement
    return scrollElement?.scrollTop || window.scrollY || 0
  }, [])

  const handleTouchStart = useCallback((e) => {
    // Только если страница прокручена вверх
    if (e.touches.length !== 1) return
    if (getScrollTop() > 0) return
=======
  const handleTouchStart = useCallback((e) => {
    // Только если страница прокручена вверх
    if (window.scrollY > 0) return
>>>>>>> a84f901 (initial)

    isTracking.current = true
    startX.current = e.touches[0].clientX
    startY.current = e.touches[0].clientY
    currentY.current = startY.current
    setIsPulling(false)
<<<<<<< HEAD
  }, [getScrollTop])

  const handleTouchMove = useCallback((e) => {
    if (!isTracking.current || isRefreshing) return
    if (getScrollTop() > 0) {
=======
  }, [])

  const handleTouchMove = useCallback((e) => {
    if (!isTracking.current || isRefreshing) return
    if (window.scrollY > 0) {
>>>>>>> a84f901 (initial)
      isTracking.current = false
      setIsPulling(false)
      setPullDistance(0)
      return
    }

    const currentX = e.touches[0].clientX
    currentY.current = e.touches[0].clientY
    const distance = currentY.current - startY.current
    const distanceX = currentX - startX.current

    if (!isPulling) {
      if (Math.abs(distance) < 6) return
      if (Math.abs(distanceX) > Math.abs(distance)) {
        isTracking.current = false
        return
      }
      setIsPulling(true)
    }

    if (distance < 0) {
      setPullDistance(0)
      return
    }

    // Применяем сопротивление
    const resistedDistance = Math.min(distance / resistance, maxPull)
    setPullDistance(resistedDistance)

    // Предотвращаем прокрутку если тянем вниз
<<<<<<< HEAD
    if (resistedDistance > 10 && e.cancelable) {
      e.preventDefault()
    }
  }, [getScrollTop, isPulling, isRefreshing, resistance, maxPull])
=======
    if (resistedDistance > 10) {
      e.preventDefault()
    }
  }, [isPulling, isRefreshing, resistance, maxPull])
>>>>>>> a84f901 (initial)

  const handleTouchEnd = useCallback(async () => {
    isTracking.current = false
    if (!isPulling) return

    setIsPulling(false)

    if (pullDistance >= threshold && !isRefreshing) {
      setIsRefreshing(true)

      // Haptic feedback
      window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('medium')

      try {
        // Вызываем обработчик обновления
        if (onRefresh) {
          await Promise.race([
            onRefresh(),
            new Promise(resolve => setTimeout(resolve, refreshTimeout))
          ])
        }
      } catch (err) {
        console.error('[PTR] Ошибка обновления:', err)
      }

      // Анимированное скрытие
      setPullDistance(0)
      setTimeout(() => {
        setIsRefreshing(false)
      }, 300)
    } else {
      setPullDistance(0)
    }
  }, [isPulling, pullDistance, threshold, isRefreshing, onRefresh, refreshTimeout])

  // Подключаем обработчики к контейнеру
  useEffect(() => {
    const container = containerRef.current || document

    container.addEventListener('touchstart', handleTouchStart, { passive: true })
    container.addEventListener('touchmove', handleTouchMove, { passive: false })
    container.addEventListener('touchend', handleTouchEnd, { passive: true })

    return () => {
      container.removeEventListener('touchstart', handleTouchStart)
      container.removeEventListener('touchmove', handleTouchMove)
      container.removeEventListener('touchend', handleTouchEnd)
    }
  }, [handleTouchStart, handleTouchMove, handleTouchEnd])

  // Прогресс от 0 до 1
  const progress = Math.min(pullDistance / threshold, 1)

  return {
    containerRef,
    isPulling,
    isRefreshing,
    pullDistance,
    progress
  }
}

export default usePullToRefresh
