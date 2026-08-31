import React, { useState } from 'react'
import { Check, ChevronRight, MessageCircle, Sparkles, Radio, Wifi, Zap, MapPin, Bot, ShieldCheck, Sun, Moon, Compass } from 'lucide-react'

function GlitterLetterText({ text, className, isEm = false }) {
  const words = text.split(' ')
  return (
    <span className={`glitter-text-wrap ${className || ''}`}>
      {words.map((word, wIdx) => (
        <span key={wIdx} className="glitter-word">
          {word.split('').map((char, cIdx) => (
            <span
              key={cIdx}
              className={`glitter-char ${isEm ? 'em-char' : 'main-char'}`}
            >
              {char}
            </span>
          ))}
          {wIdx < words.length - 1 && <span className="glitter-char space-char">&nbsp;</span>}
        </span>
      ))}
    </span>
  )
}

export function LandingView({ setView, theme, setTheme }) {
  const [spinning, setSpinning] = useState(false)

  const handleStarClick = () => {
    setSpinning(true)
    setTimeout(() => setSpinning(false), 600)
    if (setTheme) {
      setTheme(theme === 'dark' ? 'light' : 'dark')
    }
  }

  return (
    <main className="landing-view">
      <section className="landing-copy">
        <div
          className={`eyebrow red-eyebrow theme-star-badge ${spinning ? 'spin-sparkle' : ''}`}
          onClick={handleStarClick}
          title="Click star to toggle Light Crimson / Midnight Dark theme!"
          style={{ cursor: 'pointer', userSelect: 'none' }}
        >
          <Sparkles size={15} className={`star-icon ${spinning ? 'spinning-star' : ''}`} />
          <span>SWITCH ON THE WORLD</span>
          <span className="theme-toggle-indicator">
            {theme === 'dark' ? <Moon size={11} /> : <Sun size={11} />}
            {theme === 'dark' ? 'Dark Mode' : 'Light Mode'}
          </span>
        </div>
        <h1 className="glitter-heading">
          <GlitterLetterText text="Signal Selector" className="title-main" />
          <br />
          <em className="title-sub-wrap">
            <GlitterLetterText text="Connected Intelligence" isEm={true} />
          </em>
        </h1>
        <p>We help bring services and users together. Select your path to explore pincode-matched fiber plans or manage your existing service.</p>
        
        <div className="interactive-features-bar">
          <div className="feature-tag"><Zap size={13} /> 1 Gbps Max Speed</div>
          <div className="feature-tag"><MapPin size={13} /> Geocoded Coverage</div>
          <div className="feature-tag"><Bot size={13} /> Gemini AI Powered</div>
        </div>

        <div className="trust-row" style={{ marginTop: '20px' }}>
          <span><Check size={15} /> Dynamic AI Recommendation</span>
          <span><Check size={15} /> Pincode Regional Filter</span>
          <span><Check size={15} /> Grounded RAG Support</span>
          <span><Check size={15} /> Instant Plan Qualification</span>
        </div>
      </section>

      <section className="entry-card">
        <div className="entry-head">
          <span className="entry-icon red-icon"><Wifi size={20} /></span>
          <div>
            <strong>Welcome to Signal Selector</strong>
            <small>Select an option below to begin</small>
          </div>
        </div>

        <div className="entry-options">
          {/* OPTION 1: GENERAL */}
          <button onClick={() => setView('general')} className="entry-btn red-hover prodapt-click-btn">
            <span className="entry-icon red-icon"><Radio size={19} /></span>
            <span>
              <strong className="entry-title-text">GENERAL</strong>
              <small className="entry-desc-text">Explore fiber plans, verify pincode availability, get smart recommendations, and book a connection.</small>
            </span>
            <ChevronRight size={17} />
          </button>

          {/* OPTION 2: EXISTING CUSTOMERS */}
          <button onClick={() => setView('existing')} className="entry-btn red-hover prodapt-click-btn">
            <span className="entry-icon dark-icon"><MessageCircle size={19} /></span>
            <span>
              <strong className="entry-title-text">EXISTING CUSTOMERS</strong>
              <small className="entry-desc-text">Account support, connection troubleshooting, plan upgrades, and extra add-on services.</small>
            </span>
            <ChevronRight size={17} />
          </button>
        </div>

        <div className="entry-note red-note" style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', paddingTop: '4px' }}>
          <ShieldCheck size={14} style={{ color: '#E31B23' }} /> Prodapt Telecom AI Platform — Clean, Conversational & Intelligent.
        </div>
      </section>
    </main>
  )
}


