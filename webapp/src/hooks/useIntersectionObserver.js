import { useEffect, useRef, useState } from 'react'

/**
 * Hook for Intersection Observer API
 * Detects when element enters/exits viewport
 * Useful for lazy loading, infinite scroll, animations
 * 
 * @param {Object} options - IntersectionObserver options
 * @param {string} options.root - Root element (default: viewport)
 * @param {string} options.rootMargin - Margin around root (default: '0px')
 * @param {number} options.threshold - Visibility threshold 0-1 (default: 0)
 * @returns {[RefObject, boolean]} [ref, isIntersecting]
 * 
 * @example
 * const [ref, isVisible] = useIntersectionObserver({ threshold: 0.5 })
 * 
 * return (
 *   <div ref={ref}>
 *     {isVisible ? <Image /> : <Placeholder />}
 *   </div>
 * )
 */
export function useIntersectionObserver(options = {}) {
  const {
    root = null,
    rootMargin = '0px',
    threshold = 0,
  } = options

  const [isIntersecting, setIsIntersecting] = useState(false)
  const targetRef = useRef(null)

  useEffect(() => {
    const target = targetRef.current
    if (!target) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        setIsIntersecting(entry.isIntersecting)
      },
      {
        root,
        rootMargin,
        threshold,
      }
    )

    observer.observe(target)

    return () => {
      observer.disconnect()
    }
  }, [root, rootMargin, threshold])

  return [targetRef, isIntersecting]
}

/**
 * Hook for infinite scroll
 * Triggers callback when target element enters viewport
 * 
 * @param {Object} options
 * @param {Function} options.onIntersect - Called when element is visible
 * @param {boolean} options.enabled - Enable/disable observer (default: true)
 * @param {string} options.rootMargin - Load trigger distance (default: '100px')
 * @returns {RefObject} ref - Attach to trigger element
 * 
 * @example
 * const { targetRef } = useInfiniteScroll({
 *   onIntersect: () => {
 *     if (hasMore && !loading) {
 *       loadMore()
 *     }
 *   },
 *   enabled: hasMore,
 * })
 * 
 * return (
 *   <>
 *     {items.map(item => <Item key={item.id} />)}
 *     <div ref={targetRef} />
 *   </>
 * )
 */
export function useInfiniteScroll(options = {}) {
  const {
    onIntersect,
    enabled = true,
    rootMargin = '100px',
    threshold = 0,
  } = options

  const targetRef = useRef(null)
  const observerRef = useRef(null)

  useEffect(() => {
    const target = targetRef.current
    if (!target || !enabled) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && onIntersect) {
          onIntersect()
        }
      },
      {
        rootMargin,
        threshold,
      }
    )

    observer.observe(target)
    observerRef.current = observer

    return () => {
      observer.disconnect()
    }
  }, [onIntersect, enabled, rootMargin, threshold])

  return { targetRef }
}

/**
 * Hook for lazy loading images
 * Shows placeholder until image enters viewport
 * 
 * @param {string} src - Image source URL
 * @param {string} placeholder - Placeholder image URL
 * @returns {Object} { ref, src: currentSrc, isLoading }
 * 
 * @example
 * const { ref, src, isLoading } = useLazyImage(
 *   'https://example.com/image.jpg',
 *   '/placeholder.jpg'
 * )
 * 
 * return (
 *   <img 
 *     ref={ref}
 *     src={src}
 *     className={isLoading ? 'loading' : 'loaded'}
 *   />
 * )
 */
export function useLazyImage(src, placeholder = '') {
  const [currentSrc, setCurrentSrc] = useState(placeholder)
  const [isLoading, setIsLoading] = useState(true)
  const [ref, isIntersecting] = useIntersectionObserver({
    rootMargin: '50px',
    threshold: 0.01,
  })

  useEffect(() => {
    if (isIntersecting && src !== currentSrc) {
      const img = new Image()
      
      img.onload = () => {
        setCurrentSrc(src)
        setIsLoading(false)
      }
      
      img.onerror = () => {
        setIsLoading(false)
      }
      
      img.src = src
    }
  }, [isIntersecting, src, currentSrc])

  return {
    ref,
    src: currentSrc,
    isLoading,
  }
}

/**
 * Hook for viewport visibility tracking
 * Tracks if element is in viewport and percentage visible
 * 
 * @param {Object} options
 * @returns {Object} { ref, isVisible, visibilityRatio }
 * 
 * @example
 * const { ref, isVisible, visibilityRatio } = useViewportVisibility()
 * 
 * return (
 *   <div ref={ref}>
 *     {isVisible && `${Math.round(visibilityRatio * 100)}% visible`}
 *   </div>
 * )
 */
export function useViewportVisibility(options = {}) {
  const [isVisible, setIsVisible] = useState(false)
  const [visibilityRatio, setVisibilityRatio] = useState(0)
  const targetRef = useRef(null)

  useEffect(() => {
    const target = targetRef.current
    if (!target) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        setIsVisible(entry.isIntersecting)
        setVisibilityRatio(entry.intersectionRatio)
      },
      {
        threshold: [0, 0.25, 0.5, 0.75, 1],
        ...options,
      }
    )

    observer.observe(target)

    return () => {
      observer.disconnect()
    }
  }, [options])

  return {
    ref: targetRef,
    isVisible,
    visibilityRatio,
  }
}

export default useIntersectionObserver
