/**
 * Pull-to-Refresh Hook
 * Обрабатывает жест тяги вниз для обновления контента
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { getScrollContainer, getScrollTop as readScrollTop } from '../utils/scrollContainer'

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
  const resolveScrollContainer = useCallback(() => {
    const node = containerRef.current
    if (node) {
      return node.closest('.app-surface') || node
    }
    return getScrollContainer()
  }, [])

  const getScrollTop = useCallback(
    () => readScrollTop(resolveScrollContainer()),
    [resolveScrollContainer]
  )

  const handleTouchStart = useCallback((e) => {
    // Только если страница прокручена вверх
    if (getScrollTop() > 2) return

    isTracking.current = true
    startX.current = e.touches[0].clientX
    startY.current = e.touches[0].clientY
    currentY.current = startY.current
    setIsPulling(false)
  }, [getScrollTop])

  const handleTouchMove = useCallback((e) => {
    if (!isTracking.current || isRefreshing) return
    if (getScrollTop() > 2) {
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
    if (resistedDistance > 6) {
      e.preventDefault()
    }
  }, [isPulling, isRefreshing, resistance, maxPull, getScrollTop])

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
    const container = resolveScrollContainer() || document

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

