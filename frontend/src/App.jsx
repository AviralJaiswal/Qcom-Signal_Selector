import { useEffect, useMemo, useRef, useState } from 'react'
import { DayPicker } from 'react-day-picker'
import {
  ArrowLeft, CalendarDays, Check, CheckCircle2, ChevronRight, CircleHelp,
  Clock3, CreditCard, HelpCircle, MessageCircle, Send, Sparkles, UserRound, Wifi, Wrench, ShieldCheck, Zap, MapPin
} from 'lucide-react'

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'
const newSession = () => crypto.randomUUID()
const formatDateLocal = (date) => {
  if (!date) return ''
  if (typeof date === 'string') return date.slice(0, 10)
  if (date instanceof Date) {
    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    return `${year}-${month}-${day}`
  }
  return String(date)
}
const dateKey = (date) => formatDateLocal(date)

async function request(path, payload) {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), 30000)
  try {
    const response = await fetch(`${API}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: controller.signal
    })
    const body = await response.json().catch(() => ({}))
    if (!response.ok || body.success === false) {
      throw new Error(body.error || body.message || body.detail || 'Something went wrong. Please try again.')
    }
    return body.data !== undefined && body.data !== null ? { ...body, ...body.data } : body
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('The server took too long to respond. Check that the API is running.')
    throw error
  } finally {
    window.clearTimeout(timer)
  }
}

function FormattedText({ content }) {
  if (!content) return null
  const lines = content.split('\n')

  return (
    <div className="formatted-chat-content" style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
      {lines.map((line, lineIdx) => {
        const trimmed = line.trim()
        if (!trimmed) return <div key={lineIdx} style={{ height: '4px' }} />

        const parseInline = (text) => {
          const cleanText = text.replace(/\*\*\s*(.*?)\s*\*\*/g, '**$1**')
          const parts = cleanText.split(/(\*\*.*?\*\*)/g)
          return parts.map((part, pIdx) => {
            if (part.startsWith('**') && part.endsWith('**') && part.length >= 4) {
              return <strong key={pIdx} style={{ fontWeight: '700', color: 'inherit' }}>{part.slice(2, -2)}</strong>
            }
            return part
          })
        }

        if (trimmed.startsWith('* ') || trimmed.startsWith('- ') || trimmed.startsWith('• ')) {
          const bulletText = trimmed.replace(/^[\*\-\•]\s*/, '')
          return (
            <div key={lineIdx} style={{ display: 'flex', gap: '8px', alignItems: 'flex-start', lineHeight: '1.5' }}>
              <span style={{ fontWeight: 'bold', flexShrink: 0, color: 'inherit' }}>•</span>
              <div style={{ flex: 1 }}>{parseInline(bulletText)}</div>
            </div>
          )
        }

        return (
          <p key={lineIdx} style={{ margin: 0, padding: 0, lineHeight: '1.5', background: 'transparent', border: 'none', color: 'inherit' }}>
            {parseInline(line)}
          </p>
        )
      })}
    </div>
  )
}

function Summary({ icon, label, title, detail }) {
  return (
    <div className="summary-row">
      <span className="summary-icon">{icon}</span>
      <div>
        <small>{label}</small>
        <strong>{title}</strong>
        <span>{detail}</span>
      </div>
    </div>
  )
}

function ChatView({ mode, onBack }) {
  const isExisting = mode === 'existing'
  const [sessionId, setSessionId] = useState(() => {
    try {
      let key = isExisting ? 'qcom_session_id_existing' : 'qcom_session_id_general'
      sessionStorage.removeItem(key)
    } catch {}
    return (typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : 'sess-' + Math.random().toString(36).substring(2, 11) + Date.now())
  })
  const [messages, setMessages] = useState([])
  const [state, setState] = useState({})
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [customer, setCustomer] = useState({ name: '', phone: '', email: '' })
  const [addressForm, setAddressForm] = useState({ house_no: '', street: '', landmark: '' })
  const [chosenDate, setChosenDate] = useState(null)
  const [order, setOrder] = useState(null)
  const [showPaymentGateway, setShowPaymentGateway] = useState(false)
  const started = useRef(false)
  const messagesEndRef = useRef(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, busy, state, showPaymentGateway, order])

  async function send(message = '', quickAction = null, structuredFields = null, overrideSessionId = null) {
    if (busy && !overrideSessionId) return
    setBusy(true)
    setError('')
    if (message && !message.startsWith('[')) {
      setMessages((items) => [...items, { role: 'user', content: message }])
    }
    try {
      const response = await request('/chat', {
        session_id: overrideSessionId || sessionId,
        message,
        ...(quickAction ? { quick_action: quickAction } : {}),
        ...(structuredFields ? { structured_fields: structuredFields } : {})
      })
      if (overrideSessionId) {
        setMessages([{ role: 'assistant', content: response.answer }])
      } else {
        setMessages((items) => [...items, { role: 'assistant', content: response.answer }])
      }
      if (response.updated_state) {
        setState(response.updated_state)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function fetchWelcomeGreeting(sid) {
    setBusy(true)
    try {
      const res = await request('/api/v1/chat/welcome', { session_id: sid })
      const welcomeMsg = res.welcome_message || res.message
      if (welcomeMsg) {
        setMessages([{ role: 'assistant', content: welcomeMsg }])
        return
      }
    } catch (e) {
      console.warn("Welcome API fallback", e)
    } finally {
      setBusy(false)
    }
    if (isExisting) {
      send('', 'existing_customer', { is_existing_customer: true }, sid)
    } else {
      send('', 'general', null, sid)
    }
  }

  const resetSession = () => {
    try {
      let key = isExisting ? 'qcom_session_id_existing' : 'qcom_session_id_general'
      sessionStorage.removeItem(key)
    } catch {}
    const freshId = (typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : 'sess-' + Math.random().toString(36).substring(2, 11) + Date.now())
    setSessionId(freshId)
    setMessages([])
    setState({})
    setCustomer({ name: '', phone: '', email: '' })
    setAddressForm({ house_no: '', street: '', landmark: '' })
    setChosenDate(null)
    setOrder(null)
    setShowPaymentGateway(false)
    setError('')
    started.current = true
    fetchWelcomeGreeting(freshId)
  }

  useEffect(() => {
    if (!started.current) {
      started.current = true
      fetchWelcomeGreeting(sessionId)
    }
  }, [isExisting])

  const selectPlan = (plan) => {
    send(`Selected plan: ${plan.name}`, null, { action: 'PLAN_SELECTED', selected_plan: plan })
  }

  const submitAddressForm = (e) => {
    e.preventDefault()
    if (!addressForm.house_no.trim() || !addressForm.street.trim()) {
      setError('Please provide your house/flat number and street/locality.')
      return
    }
    const fullStreetAddress = [addressForm.house_no.trim(), addressForm.street.trim(), addressForm.landmark.trim()].filter(Boolean).join(', ')
    send(`Address: ${fullStreetAddress}`, null, { street_address: fullStreetAddress })
  }

  const submitCustomer = (e) => {
    e.preventDefault()
    if (!customer.name.trim() || !/^\d{10}$/.test(customer.phone) || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(customer.email)) {
      setError('Please enter a valid name, 10-digit phone number, and email address.')
      return
    }
    send('[structured customer details submitted]', null, { customer })
  }

  const selectSlot = async (slot) => {
    setBusy(true)
    setError('')
    try {
      const apptData = await request('/select-appointment', { session_id: sessionId, slot_id: slot.slot_id })
      setState((prev) => ({ ...prev, appointment: apptData }))
      setMessages((items) => [...items, {
        role: 'assistant',
        content: `Great! Your installation slot on ${slot.date} (${slot.time_window}) is reserved. Please review and confirm your booking below.`
      }])
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const confirmBookingAndPayment = async () => {
    setShowPaymentGateway(false)
    setBusy(true)
    setError('')
    try {
      const planId = state.selected_plan?.plan_id
      await request('/payment', { session_id: sessionId, plan_id: planId })
      await request('/payment/confirm', { session_id: sessionId, confirmation_code: 'DEMO-PAID' })
      const orderData = await request('/create-order', { session_id: sessionId })
      setOrder(orderData)
      setMessages((items) => [...items, {
        role: 'assistant',
        content: `🎉 Order successfully booked! Your Order ID is ${orderData.order_id || 'SIG-ORD-CONFIRMED'}. Our technical team will reach out before installation.`
      }])
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const activateAddon = (addon) => {
    send(`I would like to activate the ${addon.name} add-on service for ₹${addon.price_inr}/month.`)
  }

  const submitForm = (e) => {
    e.preventDefault()
    if (!input.trim() || busy) return
    const txt = input.trim()
    setInput('')
    send(txt)
  }

  const showAddressForm = false
  const missingCustomer = (state.missing_fields || []).filter((f) => f.startsWith('customer.'))
  const showCustomerForm = state.selected_plan && (missingCustomer.length > 0 || !state.customer)
  const showSlotPicker = state.selected_plan && state.customer && !state.appointment
  const showPaymentSummary = state.selected_plan && state.customer && state.appointment && !order

  const hasVerifiedAddress = Boolean(
    state.pincode && 
    (state.street_address || state.address_qualified || state.qualified_address?.street_address || state.qualified_address?.address_qualified)
  )
  const availablePlans = (state.plans_shown && hasVerifiedAddress) ? (state.recommended_plans || state.catalog_plans || []) : []
  const availableAddons = state.available_addons || []

  const slotList = useMemo(() => {
    const targetDate = chosenDate ? dateKey(chosenDate) : formatDateLocal(new Date())
    const compactDate = targetDate.replaceAll('-', '')
    const fdhId = state.qualified_address?.fdh_id || 'FDH-CHENNAI-01'
    return [
      { raw: '0900_1200', label: '09:00 AM - 12:00 PM' },
      { raw: '1200_1500', label: '12:00 PM - 03:00 PM' },
      { raw: '1500_1800', label: '03:00 PM - 06:00 PM' }
    ].map((slot) => ({
      slot_id: `DEMO-${fdhId}-${compactDate}-${slot.raw}`,
      date: targetDate,
      time_window: slot.label
    }))
  }, [chosenDate, state.qualified_address])


  return (
    <main className="other-view">
      <div className="other-head">
        <button className="back-link" onClick={onBack}>
          <ArrowLeft size={15} /> Home
        </button>
        <div>
          <strong>Signal Selector Assistant</strong>
          <small>{isExisting ? 'Existing Customer Support' : 'General & Plan Assistant'}</small>
        </div>
        <button className="back-link" onClick={resetSession} style={{ marginLeft: 'auto', background: '#FFF0F1', color: '#E31B23', border: '1px solid #FFCCD0', padding: '6px 12px', borderRadius: '16px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', fontWeight: '600' }}>
          <Sparkles size={13} /> New Chat
        </button>
        <span className="mode-badge red-badge" style={{ marginLeft: '10px' }}>
          <span /> {isExisting ? 'Existing Customer' : 'General Connection'}
        </span>
      </div>

      <div className="other-messages">
        {messages.map((item, index) => (
          <div className={`other-message ${item.role}`} key={index}>
            <span>{item.role === 'assistant' ? <Wifi size={14} /> : 'You'}</span>
            <div className="message-content">
              <FormattedText content={item.content} />
            </div>
          </div>
        ))}

        {availablePlans.length > 0 && !state.selected_plan && (
          <div className="chat-card-section" style={{ margin: '15px 0' }}>
            <div style={{ fontSize: '12px', fontWeight: '700', color: '#E31B23', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Sparkles size={14} />
              {isExisting ? 'Available Plan Upgrades' : 'Available Plans for Your Region'}
              {state.pincode && (
                <span style={{ marginLeft: 'auto', background: '#FFF0F1', color: '#E31B23', padding: '3px 8px', borderRadius: '12px', fontSize: '11px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <MapPin size={12} /> Pincode {state.pincode}
                </span>
              )}
            </div>
            <div className="plan-card-grid">
              {availablePlans.map((plan) => (
                <div className="wizard-plan" key={plan.plan_id} style={{ textAlign: 'left' }}>
                  <div className="plan-card-head">
                    <span>{plan.type || 'FIBER'}</span>
                    <Wifi size={13} />
                  </div>
                  <strong>{plan.name}</strong>
                  <div className="wizard-speed">{plan.speed_mbps} Mbps</div>
                  <div className="wizard-price">₹{plan.price_inr}<small>/month</small></div>
                  <button className="customer-submit red-btn" style={{ marginTop: '10px', width: '100%' }} onClick={() => selectPlan(plan)} disabled={busy}>
                    Select & Book <ChevronRight size={13} />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {isExisting && availableAddons.length > 0 && (
          <div className="chat-card-section" style={{ margin: '15px 0' }}>
            <div style={{ fontSize: '12px', fontWeight: '700', color: '#E31B23', marginBottom: '8px' }}>
              <Zap size={14} style={{ verticalAlign: 'middle', marginRight: '4px' }} />
              Popular Account Add-ons
            </div>
            <div className="plan-card-grid">
              {availableAddons.map((addon) => (
                <div className="wizard-plan" key={addon.addon_id} style={{ textAlign: 'left' }}>
                  <div className="plan-card-head">
                    <span>ADD-ON</span>
                    <Zap size={13} />
                  </div>
                  <strong>{addon.name}</strong>
                  <div className="wizard-price">₹{addon.price_inr}<small>/month</small></div>
                  <p style={{ fontSize: '11px', color: '#666', margin: '6px 0' }}>{addon.description}</p>
                  <button className="customer-submit red-btn" style={{ marginTop: '8px', width: '100%' }} onClick={() => activateAddon(addon)} disabled={busy}>
                    Activate Add-on <ChevronRight size={13} />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {showAddressForm && (
          <form className="chat-customer-form" onSubmit={submitAddressForm} style={{ margin: '15px 0' }}>
            <div className="customer-form-title">
              <MapPin size={15} /> Detailed Address Qualification (Pincode {state.pincode})
            </div>
            <p>Please enter your house/flat number and street details to fetch regional fiber plans.</p>
            <div className="customer-form-fields">
              <label>Flat / House / Building No.
                <input
                  value={addressForm.house_no}
                  onChange={(e) => setAddressForm({ ...addressForm, house_no: e.target.value })}
                  placeholder="Flat / House / Building No."
                  required
                />
              </label>
              <label>Street / Locality / Area
                <input
                  value={addressForm.street}
                  onChange={(e) => setAddressForm({ ...addressForm, street: e.target.value })}
                  placeholder="Street / Locality / Area"
                  required
                />
              </label>
              <label>Landmark (Optional)
                <input
                  value={addressForm.landmark}
                  onChange={(e) => setAddressForm({ ...addressForm, landmark: e.target.value })}
                  placeholder="Landmark (Optional)"
                />
              </label>
            </div>
            <button className="customer-submit red-btn" disabled={busy} style={{ marginTop: '12px' }}>
              Verify Location & Fetch Plans <ChevronRight size={14} />
            </button>
          </form>
        )}

        {showCustomerForm && (
          <form className="chat-customer-form" onSubmit={submitCustomer} style={{ margin: '15px 0' }}>
            <div className="customer-form-title">
              <UserRound size={15} /> Customer Details for {state.selected_plan?.name}
            </div>
            <p>Please enter your contact details to proceed with installation scheduling.</p>
            <div className="customer-form-fields">
              <label>Name <input value={customer.name} onChange={(e) => setCustomer({ ...customer, name: e.target.value })} placeholder="Full name" required /></label>
              <label>Phone <input value={customer.phone} onChange={(e) => setCustomer({ ...customer, phone: e.target.value.replace(/\D/g, '').slice(0, 10) })} placeholder="10-digit mobile number" inputMode="numeric" required /></label>
              <label>Email <input value={customer.email} onChange={(e) => setCustomer({ ...customer, email: e.target.value })} placeholder="email@example.com" type="email" required /></label>
            </div>
            <button className="customer-submit red-btn" disabled={busy}>
              Save Details & Select Slot <ChevronRight size={14} />
            </button>
          </form>
        )}

        {showSlotPicker && (
          <div className="wizard-screen" style={{ padding: '15px', background: '#fff', borderRadius: '16px', border: '1px solid #fee2e2', margin: '15px 0' }}>
            <div className="screen-kicker" style={{ color: '#E31B23' }}><CalendarDays size={14} /> INSTALLATION TIME</div>
            <h3 style={{ margin: '6px 0 12px', fontSize: '15px' }}>Choose your preferred installation slot</h3>
            <div style={{ display: 'flex', gap: '15px', flexWrap: 'wrap' }}>
              <div style={{ flex: 1, minWidth: '220px' }}>
                <DayPicker mode="single" selected={chosenDate} onSelect={setChosenDate} />
              </div>
              <div style={{ flex: 1, minWidth: '200px' }}>
                <div style={{ fontWeight: '600', fontSize: '13px', marginBottom: '8px' }}>Available Slots:</div>
                {slotList.map((slot) => (
                  <button key={slot.slot_id} className="time-slot" style={{ width: '100%', marginBottom: '8px', padding: '10px' }} onClick={() => selectSlot(slot)} disabled={busy}>
                    <Clock3 size={15} /> {slot.time_window} <ChevronRight size={15} />
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {showPaymentSummary && (
          <div className="summary-card" style={{ margin: '15px 0', padding: '16px', background: '#fff', borderRadius: '16px', border: '1px solid #fee2e2' }}>
            <div className="screen-kicker" style={{ color: '#E31B23' }}><CheckCircle2 size={14} /> READY TO BOOK</div>
            <h3 style={{ margin: '6px 0 14px', fontSize: '16px' }}>Booking Summary</h3>
            <Summary icon={<Wifi size={17} />} label="SELECTED PLAN" title={state.selected_plan?.name} detail={`${state.selected_plan?.speed_mbps} Mbps · ₹${state.selected_plan?.price_inr}/month`} />
            <Summary icon={<UserRound size={17} />} label="CUSTOMER" title={state.customer?.name} detail={`${state.customer?.phone} · ${state.customer?.email}`} />
            <Summary icon={<CalendarDays size={17} />} label="INSTALLATION" title={state.appointment?.date} detail={state.appointment?.time_window} />
            <button className="wizard-button red-btn" style={{ width: '100%', marginTop: '14px' }} onClick={() => setShowPaymentGateway(true)} disabled={busy}>
              Pay ₹{state.selected_plan?.price_inr} & Book Order <Check size={16} />
            </button>
          </div>
        )}

        {showPaymentGateway && (
          <div className="summary-card" style={{ margin: '15px 0', padding: '16px', background: '#fff', borderRadius: '16px', border: '1px solid #fee2e2' }}>
            <div className="screen-kicker" style={{ color: '#E31B23', display: 'flex', alignItems: 'center', gap: '6px', justifyContent: 'center' }}>
              <CreditCard size={18} /> DEMO PAYMENT GATEWAY
            </div>
            <h3 style={{ margin: '12px 0 4px', fontSize: '20px', textAlign: 'center' }}>
              Amount: ₹{state.selected_plan?.price_inr}
            </h3>
            <p style={{ fontSize: '12px', color: '#666', textAlign: 'center', marginBottom: '16px' }}>
              Please select a payment method to complete your booking.
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <button className="wizard-button" style={{ background: '#f8fafc', color: '#333', border: '1px solid #e2e8f0' }} onClick={confirmBookingAndPayment} disabled={busy}>
                Pay with Credit/Debit Card
              </button>
              <button className="wizard-button" style={{ background: '#f8fafc', color: '#333', border: '1px solid #e2e8f0' }} onClick={confirmBookingAndPayment} disabled={busy}>
                Pay with UPI
              </button>
              <button className="wizard-button red-btn" onClick={confirmBookingAndPayment} disabled={busy}>
                Simulate Successful Payment <Check size={16} />
              </button>
              <button className="wizard-button" style={{ background: '#fff', color: '#ef4444', border: '1px solid #ef4444' }} onClick={() => setShowPaymentGateway(false)} disabled={busy}>
                Cancel
              </button>
            </div>
          </div>
        )}

        {order && (
          <div className="success-panel" style={{ padding: '20px', textAlign: 'center', background: '#fff0f1', borderRadius: '16px', margin: '15px 0', border: '1px solid #fee2e2' }}>
            <div className="success-icon" style={{ background: '#E31B23', color: '#fff' }}><Check size={24} /></div>
            <h3 style={{ margin: '8px 0 4px', color: '#B80E16' }}>Booking Confirmed!</h3>
            <p style={{ fontSize: '13px', color: '#7f1d1d' }}>Order ID: <strong>{order.order_id}</strong></p>
          </div>
        )}

        {busy && <div className="typing"><span /><span /><span /></div>}
        {error && <p className="inline-error">{error}</p>}
        <div ref={messagesEndRef} />
      </div>

      <form className="other-composer" onSubmit={submitForm}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={isExisting ? "Provide your Name & Gmail ID, or ask about issues..." : "Type your message..."}
          disabled={busy}
        />
        <button className="red-btn" disabled={busy || !input.trim()}><Send size={16} /></button>
      </form>
    </main>
  )
}

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

      {view === 'landing' && (
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
      )}

      {view === 'general' && <ChatView mode="general" onBack={() => setView('landing')} />}
      {view === 'existing' && <ChatView mode="existing" onBack={() => setView('landing')} />}

      <footer>© 2026 Signal Selector <span>•</span> Powered by Prodapt</footer>
    </div>
  )
}


