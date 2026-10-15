import React from 'react'
import {
  Palette,
  Moon,
  Sun,
  Sparkles,
  Check,
  CheckCircle2,
  Sliders,
  FileText,
  ShieldCheck,
  Send,
  ArrowRight
} from 'lucide-react'
import { useTheme } from '../context/ThemeContext'

export default function Settings() {
  const { theme, setTheme } = useTheme()

  const THEMES = [
    {
      id: 'dark',
      name: 'Dark Theme',
      icon: Moon,
      headline: 'Deep neutral dark theme with high-contrast accents',
      description: 'The standard dark mode designed for optimal focus, zero eye fatigue, and sleek borderless prose.',
      swatches: [
        { label: 'Canvas', color: '#0d0d0d' },
        { label: 'Surface', color: '#1c1c1c' },
        { label: 'Accent', color: '#2563eb' },
        { label: 'Text', color: '#f5f5f5' }
      ]
    },
    {
      id: 'light',
      name: 'Light Theme',
      icon: Sun,
      headline: 'Minimalist, crisp white canvas following ChatGPT light mode',
      description: 'Clean off-white surfaces, crisp typography, and subtle borders inspired by ChatGPT for maximum daytime clarity.',
      swatches: [
        { label: 'Canvas', color: '#ffffff' },
        { label: 'Sidebar', color: '#f9f9f9' },
        { label: 'Accent', color: '#10a37f' },
        { label: 'Text', color: '#0d0d0d' }
      ]
    },
    {
      id: 'green',
      name: 'Green Theme',
      icon: Sparkles,
      headline: 'Pastel mint with #E3F6EF lighter and #C8EEDF darker regions',
      description: 'A soothing ice-mint aesthetic featuring #E3F6EF for light canvas areas and #C8EEDF for surfaces & sidebar.',
      swatches: [
        { label: 'Lighter (#E3F6EF)', color: '#E3F6EF' },
        { label: 'Darker (#C8EEDF)', color: '#C8EEDF' },
        { label: 'Accent', color: '#0d8a5b' },
        { label: 'Text', color: '#12382b' }
      ]
    }
  ]

  return (
    <div className="settings-page-container">
      {/* Settings Header */}
      <div className="settings-header">
        <div className="settings-header-icon">
          <Palette size={20} />
        </div>
        <div className="settings-header-text">
          <h1 className="settings-title">Workspace Settings</h1>
          <p className="settings-subtitle">
            Configure appearance, interface themes, and visual ergonomics for your knowledge search.
          </p>
        </div>
      </div>

      {/* Main Theme Section */}
      <section className="settings-card">
        <div className="settings-card-header">
          <div className="settings-card-title-group">
            <h2 className="settings-card-title">Theme & Appearance</h2>
            <p className="settings-card-desc">
              Choose your preferred visual presentation. Your selection persists across your browser sessions.
            </p>
          </div>
          <span className="settings-badge-active">
            Active: <strong>{THEMES.find(t => t.id === theme)?.name}</strong>
          </span>
        </div>

        {/* 3 Theme Choice Cards */}
        <div className="theme-grid">
          {THEMES.map((item) => {
            const isSelected = theme === item.id
            const Icon = item.icon

            return (
              <div
                key={item.id}
                className={`theme-option-card ${isSelected ? 'selected' : ''}`}
                onClick={(e) => {
                  e.preventDefault()
                  e.stopPropagation()
                  setTheme(item.id)
                }}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    e.stopPropagation()
                    setTheme(item.id)
                  }
                }}
              >
                {/* Header row */}
                <div className="theme-card-top">
                  <div className="theme-card-ident">
                    <div className="theme-icon-circle">
                      <Icon size={16} />
                    </div>
                    <div>
                      <div className="theme-option-name">{item.name}</div>
                      <span className="theme-option-tag">{item.tag}</span>
                    </div>
                  </div>

                  <div className={`theme-radio-indicator ${isSelected ? 'checked' : ''}`}>
                    {isSelected && <Check size={13} strokeWidth={3} />}
                  </div>
                </div>

                <p className="theme-option-desc">{item.description}</p>

                {/* Swatches Row */}
                <div className="theme-swatches-row">
                  {item.swatches.map((swatch, sIdx) => (
                    <div key={sIdx} className="theme-swatch-item" title={`${swatch.label}: ${swatch.color}`}>
                      <div
                        className="theme-swatch-dot"
                        style={{ backgroundColor: swatch.color }}
                      />
                      <span className="theme-swatch-label">{swatch.label}</span>
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      </section>

      {/* Live Interactive Preview Showcase */}
      <section className="settings-card preview-section">
        <div className="settings-card-header">
          <div>
            <h2 className="settings-card-title">Live Interface Preview</h2>
            <p className="settings-card-desc">
              Demonstration of how typography, citations, cards, and input fields adapt to the current <strong>{THEMES.find(t => t.id === theme)?.name}</strong>.
            </p>
          </div>
        </div>

        <div className="preview-demo-box">
          {/* Simulated Search Bar */}
          <div className="preview-search-bar">
            <span className="preview-search-placeholder">Ask a question across indexed enterprise documents...</span>
            <button type="button" className="preview-search-btn">
              <Send size={13} />
              <span>Ask AI</span>
            </button>
          </div>

          {/* Simulated Assistant Answer Card */}
          <div className="preview-assistant-card">
            <div className="preview-assistant-top">
              <div className="preview-assistant-name">
                <Sparkles size={14} className="preview-sparkle-icon" />
                <span>Enterprise AI Assistant</span>
              </div>
              <span className="preview-confidence-tag">HIGH confidence • 2 verified sources</span>
            </div>

            <p className="preview-prose">
              Based on the <strong>IT Security and Remote Work Policy</strong>, all employees working remotely are required to connect via the company VPN (<strong>OrbitSecure</strong>) prior to accessing internal repositories.
            </p>

            <div className="preview-sources-row">
              <span className="preview-source-pill active">
                <span>[1]</span>
                <span>Orbit_Security_Policy.pdf</span>
                <span className="preview-source-page">Page 1</span>
              </span>
              <span className="preview-source-pill">
                <span>[2]</span>
                <span>EKS_Handbook_v2.pdf</span>
                <span className="preview-source-page">Page 7</span>
              </span>
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}
