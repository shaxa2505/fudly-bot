import { useEffect, useState, useCallback } from 'react'
import { getScrollContainer, getScrollTop } from '../utils/scrollContainer'
import './ScrollTopButton.css'

function ScrollTopButton({ threshold = 320, label = 'Yuqoriga', className = '' }) {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const container = getScrollContainer()
    if (!container) return

    let rafId = 0
    const update = () => {
      rafId = 0
      const top = getScrollTop(container)
      setVisible(top > threshold)
    }

    const onScroll = () => {
      if (rafId) return
      rafId = window.requestAnimationFrame(update)
    }

    container.addEventListener('scroll', onScroll, { passive: true })
    update()

    return () => {
      container.removeEventListener('scroll', onScroll)
      if (rafId) window.cancelAnimationFrame(rafId)
    }
  }, [threshold])

  const handleClick = useCallback(() => {
    const container = getScrollContainer()
    if (!container) return

    const prefersReduced = window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches
    const behavior = prefersReduced ? 'auto' : 'smooth'

    if (
      container === document.body ||
      container === document.documentElement ||
      container === document.scrollingElement
    ) {
      window.scrollTo({ top: 0, behavior })
    } else if (typeof container.scrollTo === 'function') {
      container.scrollTo({ top: 0, behavior })
    } else {
      container.scrollTop = 0
    }
  }, [])

  return (
    <button
      type="button"
      className={`scroll-top-btn${visible ? ' is-visible' : ''}${className ? ` ${className}` : ''}`}
      onClick={handleClick}
      aria-label={label}
    >
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path
          d="M12 5l-6 6m6-6l6 6M12 5v14"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </button>
  )
}

export default ScrollTopButton
