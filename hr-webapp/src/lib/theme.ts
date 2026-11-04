export type ThemePreference = 'system' | 'light' | 'dark'

const KEY = 'hr3000.theme'
const media = () => window.matchMedia('(prefers-color-scheme: dark)')

export function getThemePreference(): ThemePreference {
  try {
    const value = localStorage.getItem(KEY)
    return value === 'light' || value === 'dark' ? value : 'system'
  } catch {
    return 'system'
  }
}

/** Setzt Hell/Dunkel auf <html> (siehe theme-inverted.css). */
export function applyTheme(preference: ThemePreference = getThemePreference()): void {
  const dark = preference === 'dark' || (preference === 'system' && media().matches)
  document.documentElement.classList.toggle('theme-inverted', dark)
  document.documentElement.style.colorScheme = dark ? 'dark' : 'light'
}

export function setThemePreference(preference: ThemePreference): void {
  try {
    localStorage.setItem(KEY, preference)
  } catch {
    // ohne Speicher gilt die Wahl nur bis zum Neuladen
  }
  applyTheme(preference)
}

/** Einmal beim Start: anwenden und Systemwechsel (bei "system") verfolgen. */
export function initTheme(): void {
  applyTheme()
  media().addEventListener('change', () => {
    if (getThemePreference() === 'system') applyTheme('system')
  })
}
