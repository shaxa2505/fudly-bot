import './QuantityControl.css'

function QuantityControl({
  value,
  onDecrement,
  onIncrement,
  disableDecrement = false,
  disableIncrement = false,
  size = 'md',
  className = '',
  stopPropagation = false,
  decrementLabel = "Kamaytirish",
  incrementLabel = "Ko'paytirish",
}) {
  const handleContainerClick = (event) => {
    if (stopPropagation) {
      event.stopPropagation()
    }
  }

  const handleContainerMouseDown = (event) => {
    if (stopPropagation) {
      event.stopPropagation()
    }
  }

  return (
    <div
      className={`quantity-control quantity-control--${size} ${className}`.trim()}
      onClick={handleContainerClick}
      onMouseDown={handleContainerMouseDown}
    >
      <button
        type="button"
        className="quantity-control__btn quantity-control__btn--minus"
        onClick={onDecrement}
        disabled={disableDecrement}
        aria-label={decrementLabel}
      >
        -
      </button>
      <span className="quantity-control__value" aria-live="polite">
        {value}
      </span>
      <button
        type="button"
        className="quantity-control__btn quantity-control__btn--plus"
        onClick={onIncrement}
        disabled={disableIncrement}
        aria-label={incrementLabel}
      >
        +
      </button>
    </div>
  )
}

export default QuantityControl

