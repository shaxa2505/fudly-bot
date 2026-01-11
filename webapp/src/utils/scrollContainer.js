export const getScrollContainer = () =>
  document.querySelector('.app-surface') ||
  document.scrollingElement ||
  document.documentElement

export const getScrollTop = (target) => {
  const container = target || getScrollContainer()
  if (!container) return 0
  if (
    container === document.body ||
    container === document.documentElement ||
    container === document.scrollingElement
  ) {
    return window.scrollY || window.pageYOffset || container.scrollTop || 0
  }
  return container.scrollTop || 0
}
