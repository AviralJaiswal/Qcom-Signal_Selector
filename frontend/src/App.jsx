import React, { useState } from 'react'
import { CircleHelp } from 'lucide-react'
import { LandingView } from './views/LandingView'
import { GeneralChatView } from './views/GeneralChatView'
import { ExistingChatView } from './views/ExistingChatView'

export function App() {
  const [view, setView] = useState('landing')

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand" style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '9px' }} onClick={() => setView('landing')}>
          <div style={{ display: 'flex', alignItems: 'flex-start', paddingTop: '2px' }}>
            <span style={{ fontSize: '22px', fontWeight: '800', color: '#E31B23', letterSpacing: '-0.5px', fontFamily: "'Arial', sans-serif", lineHeight: '1' }}>
              Prodapt
            </span>
            <svg width="12" height="12" viewBox="0 0 10 10" style={{ fill: '#E31B23', marginLeft: '2px', marginTop: '10px' }}>
              <polygon points="0,0 10,0 10,10" />
            </svg>
          </div>
          <span style={{ color: '#e5e7eb', fontSize: '20px', fontWeight: '300', margin: '0 2px' }}>|</span>
          <span style={{ fontSize: '18px', fontWeight: '700', color: '#1f2937' }}>Signal Selector</span>
        </div>
        <div className="top-status">
          <span className="status-dot green-dot" /> Online <span className="help"><CircleHelp size={16} /></span>
        </div>
      </header>

      {view === 'landing' && <LandingView setView={setView} />}
      {view === 'general' && <GeneralChatView onBack={() => setView('landing')} />}
      {view === 'existing' && <ExistingChatView onBack={() => setView('landing')} />}

      <footer>© 2026 Signal Selector <span>•</span> Powered by Prodapt</footer>
    </div>
  )
}
