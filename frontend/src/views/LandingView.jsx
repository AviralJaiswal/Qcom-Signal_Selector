import React from 'react'
import { Check, ChevronRight, MessageCircle, Sparkles, Wifi } from 'lucide-react'

export function LandingView({ setView }) {
  return (
    <main className="landing-view">
      <section className="landing-copy">
        <div className="eyebrow red-eyebrow"><Sparkles size={15} /> SWITCH ON THE WORLD</div>
        <h1>Signal Selector<br /><em>Connected Intelligence.</em></h1>
        <p>We help bring services and users together. Select your path to explore pincode-matched fiber plans or manage your existing service.</p>
        <div className="trust-row">
          <span><Check size={15} /> Dynamic AI Recommendation</span>
          <span><Check size={15} /> Pincode Regional Filter</span>
          <span><Check size={15} /> Grounded RAG Support</span>
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
          <button onClick={() => setView('general')} className="entry-btn red-hover">
            <span className="entry-icon red-icon"><Wifi size={19} /></span>
            <span>
              <strong>GENERAL</strong>
              <small>Explore fiber plans, verify pincode availability, get smart recommendations, and book a connection.</small>
            </span>
            <ChevronRight size={17} />
          </button>

          {/* OPTION 2: EXISTING CUSTOMERS */}
          <button onClick={() => setView('existing')} className="entry-btn red-hover">
            <span className="entry-icon dark-icon"><MessageCircle size={19} /></span>
            <span>
              <strong>EXISTING CUSTOMERS</strong>
              <small>Account support, connection troubleshooting, plan upgrades, and extra add-on services.</small>
            </span>
            <ChevronRight size={17} />
          </button>
        </div>

        <div className="entry-note red-note">
          <Check size={13} /> Prodapt Telecom AI Platform — Clean & Conversational.
        </div>
      </section>
    </main>
  )
}
