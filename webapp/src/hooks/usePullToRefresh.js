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
  const currentY = useRef(0)
  const containerRef = useRef(null)

  const handleTouchStart = useCallback((e) => {
    // Только если страница прокручена вверх
    if (window.scrollY > 0) return

    startY.current = e.touches[0].clientY
    currentY.current = startY.current
    setIsPulling(true)
  }, [])

  const handleTouchMove = useCallback((e) => {
    if (!isPulling || isRefreshing) return
    if (window.scrollY > 0) {
      setIsPulling(false)
      setPullDistance(0)
      return
    }

    currentY.current = e.touches[0].clientY
    const distance = currentY.current - startY.current

    if (distance < 0) {
      setPullDistance(0)
      return
    }

    // Применяем сопротивление
    const resistedDistance = Math.min(distance / resistance, maxPull)
    setPullDistance(resistedDistance)

    // Предотвращаем прокрутку если тянем вниз
    if (resistedDistance > 10) {
      e.preventDefault()
    }
  }, [isPulling, isRefreshing, resistance, maxPull])

  const handleTouchEnd = useCallback(async () => {
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
