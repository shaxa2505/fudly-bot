import { getCurrentUser } from './auth'

const normalizeCode = (value) => {
  const raw = String(value || '').trim().toLowerCase()
  if (raw.startsWith('ru')) return 'ru'
  return 'uz'
}

export const resolveUiLanguage = (user = null) => {
  const currentUser = getCurrentUser()
  const telegramCode = window.Telegram?.WebApp?.initDataUnsafe?.user?.language_code
  const candidate =
    user?.language ||
    user?.language_code ||
    currentUser?.language ||
    currentUser?.language_code ||
    telegramCode ||
    'uz'

  return normalizeCode(candidate)
}

export const tByLang = (lang, ruText, uzText) => (
  normalizeCode(lang) === 'ru' ? ruText : uzText
)

