import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { AuthProvider } from './context/AuthContext'
import { ThemeProvider } from './context/ThemeContext'
import { ChatProvider } from './context/ChatContext'

// Ensure browser tab immediately updates and bypasses browser favicon cache
(() => {
  try {
    const existing = document.querySelector("link[rel*='icon']");
    const link = existing || document.createElement('link');
    link.type = 'image/svg+xml';
    link.rel = 'icon';
    link.href = `/marvo.svg?v=${Date.now()}`;
    if (!existing) document.head.appendChild(link);
  } catch (_) {}
})();

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ThemeProvider>
      <AuthProvider>
        <ChatProvider>
          <App />
        </ChatProvider>
      </AuthProvider>
    </ThemeProvider>
  </StrictMode>,
)
