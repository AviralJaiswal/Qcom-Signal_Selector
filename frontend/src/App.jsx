import React, { useState } from 'react'
import { CircleHelp, Sparkles, Home, Wifi, UserRound } from 'lucide-react'
import { LandingView } from './views/LandingView'
import { GeneralChatView } from './views/GeneralChatView'
import { ExistingChatView } from './views/ExistingChatView'

export function App() {
  const [view, setView] = useState('landing')
  const [theme, setTheme] = useState('light')

  return (
    <div className={`app-shell ${theme === 'dark' ? 'dark-mode' : ''}`}>
      <header className="topbar">
        {/* Brand Container */}
        <div className="brand brand-interactive" onClick={() => setView('landing')}>
          <div className="prodapt-brand-logo">
            <span className="prodapt-brand-text">Prodapt</span>
            <svg width="10" height="10" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg" className="prodapt-mark-svg">
              <polygon points="0,0 12,0 12,12" fill="#E31B23" />
            </svg>
          </div>
          <span className="brand-divider">|</span>
          <span className="brand-title">Signal Selector</span>
          <span className="brand-ai-badge">
            <Sparkles size={13} /> Telecom AI
          </span>
        </div>

        {/* Live Radar Status Indicator */}
        <div className="top-status">
          <div className="live-status-badge">
            <span className="radar-ping" />
            <span className="status-dot green-dot" />
            <span className="status-text">Online</span>
          </div>
          <span className="help" title="Telecom AI Assistant Help"><CircleHelp size={16} /></span>
        </div>
      </header>

      {view === 'landing' && <LandingView setView={setView} theme={theme} setTheme={setTheme} />}
      {view === 'general' && <GeneralChatView onBack={() => setView('landing')} />}
      {view === 'existing' && <ExistingChatView onBack={() => setView('landing')} />}

      <footer>© 2026 Signal Selector <span>•</span> Powered by Prodapt Telecom AI</footer>
    </div>
  )
}

