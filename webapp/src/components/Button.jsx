import { memo, forwardRef } from 'react'
import './Button.css'

/**
 * Unified Button Component
 *
 * @param {Object} props
 * @param {'primary' | 'secondary' | 'ghost' | 'danger' | 'accent'} variant - Button style variant
 * @param {'sm' | 'md' | 'lg'} size - Button size
 * @param {boolean} fullWidth - Whether button takes full width
 * @param {boolean} loading - Show loading spinner
 * @param {boolean} disabled - Disable button
 * @param {React.ReactNode} leftIcon - Icon on the left
 * @param {React.ReactNode} rightIcon - Icon on the right
 * @param {React.ReactNode} children - Button content
 */
const Button = memo(forwardRef(function Button(
  {
    variant = 'primary',
    size = 'md',
    fullWidth = false,
    loading = false,
    disabled = false,
    leftIcon,
    rightIcon,
    children,
    className = '',
    onClick,
    type = 'button',
    ...props
  },
  ref
) {
  const handleClick = (e) => {
    if (loading || disabled) return

    // Haptic feedback
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light')

    onClick?.(e)
  }

  const classNames = [
    'btn',
    `btn-${variant}`,
    `btn-${size}`,
    fullWidth && 'btn-full-width',
    loading && 'btn-loading',
    disabled && 'btn-disabled',
    className
  ].filter(Boolean).join(' ')

  return (
    <button
      ref={ref}
      type={type}
      className={classNames}
      onClick={handleClick}
      disabled={disabled || loading}
      {...props}
    >
      {loading && (
        <span className="btn-spinner">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
            <circle
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="3"
              strokeLinecap="round"
              strokeDasharray="32"
              strokeDashoffset="12"
            />
          </svg>
        </span>
      )}
      {!loading && leftIcon && <span className="btn-icon btn-icon-left">{leftIcon}</span>}
      <span className="btn-text">{children}</span>
      {!loading && rightIcon && <span className="btn-icon btn-icon-right">{rightIcon}</span>}
    </button>
  )
}))

export default Button
