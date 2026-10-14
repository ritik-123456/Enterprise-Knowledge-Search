import { createContext, useContext, useState, useEffect } from 'react'

const ThemeContext = createContext({
  theme: 'dark',
  setTheme: () => {}
})

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(() => {
    try {
      const saved = localStorage.getItem('eks_theme')
      if (saved && ['dark', 'light', 'green'].includes(saved)) {
        return saved
      }
    } catch {
      // ignore
    }
    return 'dark'
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    try {
      localStorage.setItem('eks_theme', theme)
    } catch {
      // ignore
    }
  }, [theme])

  const setTheme = (newTheme) => {
    if (['dark', 'light', 'green'].includes(newTheme)) {
      setThemeState(newTheme)
    }
  }

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  const context = useContext(ThemeContext)
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider')
  }
  return context
}
