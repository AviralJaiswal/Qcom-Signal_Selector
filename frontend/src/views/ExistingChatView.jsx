import React, { useEffect, useMemo, useRef, useState } from 'react'
import { DayPicker } from 'react-day-picker'
import 'react-day-picker/style.css'
import { ArrowLeft, CalendarDays, Check, CheckCircle2, ChevronRight, CreditCard, Send, Sparkles, UserRound, Wifi, MapPin, Zap } from 'lucide-react'
import { request, dateKey, loadRazorpay } from '../utils/api'
import { FormattedText } from '../components/FormattedText'
import { Summary } from '../components/Summary'

export function ExistingChatView({ onBack }) {
  const mode = "existing";
  const isExisting = mode === 'existing'
  const [sessionId, setSessionId] = useState(() => {
    try {
      let key = isExisting ? 'qcom_session_id_existing' : 'qcom_session_id_general'
      sessionStorage.removeItem(key)
    } catch { }
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
    const mergedFields = {
      ...(isExisting ? { is_existing_customer: true } : {}),
      ...(structuredFields || {})
    }
    try {
      const response = await request('/chat', {
        session_id: overrideSessionId || sessionId,
        message,
        ...(quickAction ? { quick_action: quickAction } : {}),
        structured_fields: Object.keys(mergedFields).length > 0 ? mergedFields : null
      })

      const rawPlans = (response.sources && Array.isArray(response.sources) && response.sources.length > 0 && response.sources[0]?.price_inr !== undefined)
        ? response.sources
        : ((response.updated_state?.plans_shown && response.updated_state?.address_qualified && response.updated_state?.address_confirmed)
          ? (response.updated_state?.catalog_plans || response.updated_state?.recommended_plans || [])
          : [])

      const isPlanDiscovery =
        (response.intent === 'PLANS_DISCOVERED' || response.workflow_state === 'PLAN_SELECTION' || response.workflowState === 'PLAN_SELECTION') &&
        rawPlans.length > 0

      setMessages((items) => {
        const alreadyHasPlans = items.some((m) => m.plans && m.plans.length > 0)
        const shouldAttachPlans = (isPlanDiscovery && !alreadyHasPlans) || (rawPlans.length > 0 && !alreadyHasPlans && (response.answer?.includes('plans for') || response.answer?.includes('plans available') || response.answer?.includes('suits you best')))
        const newAssistantMsg = {
          role: 'assistant',
          content: response.answer,
          ...(shouldAttachPlans ? { plans: rawPlans } : {}),
          ...(response.recommended_plan ? { recommended_plan: response.recommended_plan } : {})
        }
        if (overrideSessionId) {
          return [newAssistantMsg]
        }
        return [...items, newAssistantMsg]
      })

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
      const res = await request('/api/v1/assistant/welcome', { sessionId: sid, profile: 'general' })
      const welcomeMsg = res.response || res.welcome_message || res.message
      if (welcomeMsg) {
        setMessages([{ role: 'assistant', content: isExisting ? `📌 **Existing Customer Portal (UI Highlight)**\n\n*Note: Backend existing customer lookup is disabled. You can switch to General Connection to chat with our dynamic AI assistant, check coverage, explore plans, and test the order flow!*\n\n${welcomeMsg}` : welcomeMsg }])
        return
      }
    } catch (e) {
      console.warn("Welcome API fallback", e)
    } finally {
      setBusy(false)
    }
    send('', 'general', null, sid)
  }

  const resetSession = () => {
    try {
      let key = isExisting ? 'qcom_session_id_existing' : 'qcom_session_id_general'
      sessionStorage.removeItem(key)
    } catch { }
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
    const customerMsg = `Name: ${customer.name.trim()}\nPhone: ${customer.phone.trim()}\nEmail: ${customer.email.trim()}`
    send(customerMsg, null, { customer })
  }

  const today = useMemo(() => {
    const d = new Date()
    d.setHours(0, 0, 0, 0)
    return d
  }, [])

  const selectSlot = async (slot) => {
    setBusy(true)
    setError('')
    const dateObj = new Date(slot.date + 'T00:00:00')
    const dateFormatted = !isNaN(dateObj)
      ? dateObj.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })
      : slot.date

    const userMsg = `📅 Selected Installation Slot: ${dateFormatted} (${slot.time_window})`
    setMessages((items) => [...items, { role: 'user', content: userMsg }])

    try {
      const apptData = await request('/select-appointment', { session_id: sessionId, slot_id: slot.slot_id })
      setState((prev) => ({ ...prev, appointment: apptData }))
      setMessages((items) => [...items, {
        role: 'assistant',
        content: `Great! Your installation appointment on **${dateFormatted}** (${slot.time_window}) is reserved.\n\n**Booking Summary:**\n- **Plan:** ${state.selected_plan?.name} (${state.selected_plan?.speed_mbps} Mbps) at ₹${state.selected_plan?.price_inr}/month\n- **Customer:** ${state.customer?.name} | ${state.customer?.phone} | ${state.customer?.email}\n\nPlease select a payment method below to complete your booking.`
      }])
      setShowPaymentGateway(true)
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
      const paymentData = await request('/payment', { session_id: sessionId, plan_id: planId })

      if (paymentData.razorpay_order_id) {
        const resLoaded = await loadRazorpay()
        if (!resLoaded) {
          setError('Failed to load Razorpay SDK')
          setBusy(false)
          return
        }

        const options = {
          key: paymentData.razorpay_key_id,
          amount: paymentData.amount_inr * 100,
          currency: 'INR',
          name: 'Signal Selector',
          description: 'Plan Subscription',
          order_id: paymentData.razorpay_order_id,
          prefill: {
            name: state.customer?.name || '',
            email: state.customer?.email || '',
            contact: state.customer?.phone || ''
          },
          handler: async function (response) {
            try {
              setBusy(true)
              await request('/payment/confirm', { session_id: sessionId, confirmation_code: response.razorpay_payment_id })
              const orderData = await request('/create-order', { session_id: sessionId })
              setOrder(orderData)
              setMessages((items) => [...items, {
                role: 'assistant',
                content: `🎉 **Booking Confirmed!**\n\nCongratulations ${state.customer?.name}! Your order **${orderData.order_id || 'SIG-ORD-CONFIRMED'}** has been confirmed successfully.\n\n**Plan Details:**\n• Plan: ${state.selected_plan?.name} (${state.selected_plan?.speed_mbps} Mbps)\n• Price: ₹${state.selected_plan?.price_inr}/month\n\n**Customer Details:**\n• Name: ${state.customer?.name}\n• Contact: ${state.customer?.phone} | ${state.customer?.email}\n\n**Installation Details:**\n• Date: ${state.appointment?.date || 'Tomorrow'}\n• Time: ${state.appointment?.time_window || 'Morning'}\n\nOur technician will contact you prior to arrival.`
              }])
            } catch (err) {
              setError(err.message)
            } finally {
              setBusy(false)
            }
          },
          modal: {
            ondismiss: function () {
              setBusy(false)
            }
          }
        }
        const rzp = new window.Razorpay(options)
        rzp.open()
      } else {
        await request('/payment/confirm', { session_id: sessionId, confirmation_code: 'DEMO-PAID' })
        const orderData = await request('/create-order', { session_id: sessionId })
        setOrder(orderData)
        setMessages((items) => [...items, {
          role: 'assistant',
          content: `🎉 **Booking Confirmed!**\n\nCongratulations ${state.customer?.name}! Your order **${orderData.order_id || 'SIG-ORD-CONFIRMED'}** has been confirmed successfully.\n\n**Plan Details:**\n• Plan: ${state.selected_plan?.name} (${state.selected_plan?.speed_mbps} Mbps)\n• Price: ₹${state.selected_plan?.price_inr}/month\n\n**Customer Details:**\n• Name: ${state.customer?.name}\n• Contact: ${state.customer?.phone} | ${state.customer?.email}\n\n**Installation Details:**\n• Date: ${state.appointment?.date || 'Tomorrow'}\n• Time: ${state.appointment?.time_window || 'Morning'}\n\nOur technician will contact you prior to arrival.`
        }])
        setBusy(false)
      }
    } catch (err) {
      setError(err.message)
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
  const showCustomerForm = !isExisting && state.selected_plan && (missingCustomer.length > 0 || !state.customer)
  const showSlotPicker = !isExisting && state.selected_plan && state.customer && !state.appointment
  const showPaymentSummary = false

  const hasVerifiedAddress = Boolean(
    state.pincode &&
    (state.street_address || state.address_qualified || state.qualified_address?.street_address || state.qualified_address?.address_qualified)
  )
  const availablePlans = ((state.plans_shown && state.address_qualified && state.address_confirmed) || isExisting) ? (state.catalog_plans || state.recommended_plans || []) : []
  const availableAddons = state.available_addons || []

  const slotList = useMemo(() => {
    const targetDate = chosenDate ? dateKey(chosenDate) : dateKey(today)
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
  }, [chosenDate, today, state.qualified_address])


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
        {(() => {
          let cardRendered = false;
          const renderedMessages = messages.map((item, index) => {
            const isHiddenUserMessage = item.role === 'user' && (item.content.startsWith('Selected plan:') || item.content.startsWith('📅 Selected Installation Slot:'));
            if (isHiddenUserMessage) return null;

            return (
              <div key={index}>
                <div className={`other-message ${item.role}`}>
                  <span>{item.role === 'assistant' ? <Wifi size={14} /> : 'You'}</span>
                  <div className="message-content" style={item.role === 'user' && item.content.includes('Name:') && item.content.includes('Email:') ? { background: 'transparent', border: 'none', padding: 0, width: '100%', maxWidth: '100%' } : {}}>
                    {item.role === 'user' && item.content.includes('Name:') && item.content.includes('Phone:') && item.content.includes('Email:') ? (() => {
                      const nameMatch = item.content.match(/Name:\s*(.*)/);
                      const phoneMatch = item.content.match(/Phone:\s*(.*)/);
                      const emailMatch = item.content.match(/Email:\s*(.*)/);
                      const custName = nameMatch ? nameMatch[1].trim() : '';
                      const custPhone = phoneMatch ? phoneMatch[1].trim() : '';
                      const custEmail = emailMatch ? emailMatch[1].trim() : '';
                      return (
                        <div className="chat-customer-form" style={{ margin: '0 0 10px 0', border: '1px solid #a7f3d0', background: 'linear-gradient(135deg, #f0fdf4, #ffffff)', boxShadow: '0 10px 28px rgba(16, 185, 129, 0.08)' }}>
                          <div className="customer-form-title" style={{ color: '#059669' }}>
                            <UserRound size={15} style={{ color: '#10B981' }} /> Customer Details Saved
                            <span style={{ marginLeft: 'auto', background: '#D1FAE5', color: '#047857', padding: '3px 10px', borderRadius: '12px', fontSize: '11px', fontWeight: '700', display: 'flex', alignItems: 'center', gap: '4px' }}>
                              <CheckCircle2 size={13} /> Saved ✓
                            </span>
                          </div>
                          <p style={{ margin: '6px 0 13px', color: '#059669', fontSize: '11px' }}>Your contact information has been verified and recorded.</p>
                          <div className="customer-form-fields">
                            <label>Name
                              <input value={custName} readOnly style={{ borderColor: '#6ee7b7', background: '#f0fdf4', color: '#065f46', cursor: 'default', fontWeight: '600' }} />
                            </label>
                            <label>Phone
                              <input value={custPhone} readOnly style={{ borderColor: '#6ee7b7', background: '#f0fdf4', color: '#065f46', cursor: 'default', fontWeight: '600' }} />
                            </label>
                            <label>Email
                              <input value={custEmail} readOnly style={{ borderColor: '#6ee7b7', background: '#f0fdf4', color: '#065f46', cursor: 'default', fontWeight: '600' }} />
                            </label>
                          </div>
                        </div>
                      );
                    })() : (
                      <FormattedText content={item.content} />
                    )}
                    {item.recommended_plan && (() => {
                      const isSelected = state.selected_plan && (state.selected_plan.plan_id === item.recommended_plan.plan_id || state.selected_plan.name === item.recommended_plan.name);
                      const isAnyPlanSelected = Boolean(state.selected_plan);
                      return (
                        <div className="wizard-plan" style={{ marginTop: '12px', textAlign: 'left', background: isSelected ? '#ECFDF5' : '#FFFFFF', border: isSelected ? '2px solid #10B981' : '2px solid #E31B23', borderRadius: '14px', padding: '14px', boxShadow: '0 4px 12px rgba(227, 27, 35, 0.08)' }}>
                          <div className="plan-card-head" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                            <span style={{ background: isSelected ? '#D1FAE5' : '#FFF0F1', color: isSelected ? '#059669' : '#E31B23', padding: '3px 10px', borderRadius: '12px', fontWeight: '700', fontSize: '10px' }}>
                              <Sparkles size={11} style={{ verticalAlign: 'middle', marginRight: '4px' }} />
                              {isSelected ? 'ACTIVE SELECTION' : 'RECOMMENDED MATCH'}
                            </span>
                            <Wifi size={14} style={{ color: isSelected ? '#059669' : '#E31B23' }} />
                          </div>
                          <strong style={{ fontSize: '15px', color: isSelected ? '#065F46' : '#1F2937', display: 'block', marginBottom: '2px' }}>{item.recommended_plan.name}</strong>
                          {item.recommended_plan.speed_mbps && (
                            <div className="wizard-speed" style={{ color: isSelected ? '#047857' : '#E31B23', fontSize: '13px', fontWeight: '600', marginBottom: '4px' }}>
                              {item.recommended_plan.speed_mbps} Mbps Speed
                            </div>
                          )}
                          <div className="wizard-price" style={{ color: isSelected ? '#065F46' : '#111827', fontSize: '17px', fontWeight: '700', marginBottom: '6px' }}>
                            ₹{item.recommended_plan.price_inr}<small style={{ color: isSelected ? '#047857' : '#6B7280', fontSize: '11px', fontWeight: '400' }}>/month</small>
                          </div>
                          {item.recommended_plan.description && (
                            <p style={{ fontSize: '11px', color: isSelected ? '#047857' : '#4B5563', margin: '4px 0 10px' }}>{item.recommended_plan.description}</p>
                          )}
                          <button
                            className={`customer-submit ${isSelected ? 'green-btn' : 'red-btn'}`}
                            style={{ marginTop: '6px', width: '100%', padding: '8px 12px', fontSize: '13px', backgroundColor: isSelected ? '#10B981' : (isAnyPlanSelected ? '#9CA3AF' : undefined), opacity: (!isSelected && isAnyPlanSelected) ? 0.6 : 1, cursor: isAnyPlanSelected ? 'default' : 'pointer' }}
                            onClick={() => !isAnyPlanSelected && selectPlan(item.recommended_plan)}
                            disabled={busy || isAnyPlanSelected}
                          >
                            {isSelected ? 'Selected ✓' : (isAnyPlanSelected ? 'Plan Selected' : 'Select & Book')} <ChevronRight size={13} />
                          </button>
                        </div>
                      );
                    })()}
                    {item.role === 'assistant' && (item.content.includes('installation appointment slot') || item.content.includes('Contact details saved')) && (
                      <div style={{ padding: '24px', background: '#ffffff', borderRadius: '12px', border: '1px solid #F0EDED', marginTop: '12px', boxShadow: '0 2px 12px rgba(0,0,0,0.04)', textAlign: 'left', width: '100%', boxSizing: 'border-box' }}>
                        <h3 style={{ margin: '0 0 20px 0', fontSize: '16px', fontWeight: '600', color: '#1a1a1a', letterSpacing: '-0.3px' }}>Pick a date and time</h3>
                        <div style={{ display: 'flex', gap: '28px', flexWrap: 'wrap', alignItems: 'flex-start' }}>
                          <style>{`
                            .calendly-cal.rdp-root {
                              --rdp-accent-color: #E31B23;
                              --rdp-accent-background-color: #E31B23;
                              --rdp-day-height: 40px;
                              --rdp-day-width: 40px;
                              --rdp-day_button-height: 36px;
                              --rdp-day_button-width: 36px;
                              --rdp-day_button-border-radius: 50%;
                              --rdp-selected-border: 2px solid transparent;
                              --rdp-today-color: #E31B23;
                              --rdp-nav-height: 2.5rem;
                              --rdp-nav_button-height: 2rem;
                              --rdp-nav_button-width: 2rem;
                              --rdp-disabled-opacity: 0.3;
                              font-family: inherit;
                              font-size: 14px;
                            }
                            .calendly-cal .rdp-month_caption { font-size: 15px; font-weight: 500; color: #1a1a1a; }
                            .calendly-cal .rdp-weekday { font-size: 12px; font-weight: 500; color: #999; opacity: 1; text-transform: capitalize; }
                            .calendly-cal .rdp-day_button { font-size: 14px; font-weight: 400; color: #333; transition: background 0.15s, color 0.15s; }
                            .calendly-cal .rdp-day_button:hover { background: #F5F5F5; }
                            .calendly-cal .rdp-selected .rdp-day_button { background-color: #E31B23 !important; color: #fff !important; font-weight: 500; }
                            .calendly-cal .rdp-today:not(.rdp-selected) .rdp-day_button { color: #E31B23; font-weight: 600; }
                            .calendly-cal .rdp-chevron { fill: #666; }
                            .calendly-cal .rdp-button_next, .calendly-cal .rdp-button_previous { border-radius: 6px; }
                            .calendly-cal .rdp-button_next:hover, .calendly-cal .rdp-button_previous:hover { background: #F5F5F5; }
                            .calendly-cal .rdp-disabled .rdp-day_button { color: #ddd; }
                            .calendly-cal .rdp-disabled .rdp-day_button:hover { background: transparent; cursor: default; }

                            .cal-slot { width: 100%; margin-bottom: 10px; padding: 14px 16px; border-radius: 6px; border: 1px solid #E8D5CF; background: #fff; cursor: pointer; text-align: center; font-weight: 500; font-size: 14px; color: #E31B23; transition: all 0.15s; outline: none; display: block; }
                            .cal-slot:hover:not(:disabled) { border-color: #E31B23; background: #FFF9F8; }
                            .cal-slot:disabled { opacity: 0.4; cursor: default; }
                            .cal-slot.cal-slot--active { background: #333; color: #fff; border-color: #333; font-weight: 600; }
                          `}</style>

                          <div style={{ flex: '1 1 280px', minWidth: '270px', pointerEvents: state.appointment ? 'none' : 'auto', opacity: state.appointment ? 0.8 : 1 }}>
                            <DayPicker
                              className="calendly-cal"
                              mode="single"
                              selected={state.appointment?.date ? new Date(state.appointment.date + 'T00:00:00') : (chosenDate || today)}
                              onSelect={(d) => !state.appointment && d && setChosenDate(d)}
                              disabled={state.appointment ? { before: new Date(2000, 0, 1), after: new Date(2099, 11, 31) } : { before: today }}
                              fromDate={today}
                              defaultMonth={state.appointment?.date ? new Date(state.appointment.date + 'T00:00:00') : (chosenDate || today)}
                            />
                          </div>

                          <div style={{ flex: '1 1 180px', minWidth: '170px', paddingTop: '2px' }}>
                            <div style={{ fontSize: '15px', fontWeight: '500', color: '#1a1a1a', marginBottom: '16px' }}>
                              {(() => {
                                const d = new Date((state.appointment?.date || (chosenDate ? dateKey(chosenDate) : dateKey(today))) + 'T00:00:00');
                                return isNaN(d) ? '' : d.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });
                              })()}
                            </div>
                            {slotList.map((slot) => {
                              const isSelected = state.appointment && state.appointment.slot_id === slot.slot_id;
                              const isAppointmentFixed = Boolean(state.appointment);
                              return (
                                <button
                                  key={slot.slot_id}
                                  className={`cal-slot${isSelected ? ' cal-slot--active' : ''}`}
                                  onClick={() => !isAppointmentFixed && selectSlot(slot)}
                                  disabled={busy || (isAppointmentFixed && !isSelected)}
                                >
                                  {slot.time_window}
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {item.plans && item.plans.length > 0 && (
                  <div className="chat-card-section" style={{ margin: '15px 0' }}>
                    <div style={{ fontSize: '12px', fontWeight: '700', color: '#E31B23', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <Sparkles size={14} />
                      {item.plans[0]?.addon_id ? 'Available Add-on Services' : (isExisting ? 'Available Plan Upgrades' : 'Available Plans for Your Region')}
                      {state.pincode && (
                        <span style={{ marginLeft: 'auto', background: '#FFF0F1', color: '#E31B23', padding: '3px 8px', borderRadius: '12px', fontSize: '11px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <MapPin size={12} /> Pincode {state.pincode}
                        </span>
                      )}
                    </div>
                    <div className="plan-card-grid">
                      {item.plans.map((plan) => {
                        const isSelected = state.selected_plan && (state.selected_plan.plan_id === plan.plan_id || state.selected_plan.name === plan.name);
                        const isAnyPlanSelected = Boolean(state.selected_plan);
                        return (
                          <div className="wizard-plan" key={plan.plan_id || plan.addon_id || plan.name} style={{ textAlign: 'left', border: isSelected ? '2px solid #10B981' : undefined, background: isSelected ? '#ECFDF5' : undefined }}>
                            <div className="plan-card-head">
                              <span style={{ color: isSelected ? '#059669' : undefined, background: isSelected ? '#D1FAE5' : undefined }}>
                                {isSelected ? 'SELECTED' : (plan.addon_id ? 'ADD-ON' : (plan.type || 'FIBER'))}
                              </span>
                              {plan.addon_id ? <Zap size={13} /> : <Wifi size={13} style={{ color: isSelected ? '#059669' : undefined }} />}
                            </div>
                            <strong style={{ color: isSelected ? '#065F46' : undefined }}>{plan.name}</strong>
                            {plan.speed_mbps && <div className="wizard-speed" style={{ color: isSelected ? '#047857' : undefined }}>{plan.speed_mbps} Mbps</div>}
                            <div className="wizard-price" style={{ color: isSelected ? '#065F46' : undefined }}>₹{plan.price_inr}<small style={{ color: isSelected ? '#047857' : undefined }}>/month</small></div>
                            {plan.description && <p style={{ fontSize: '11px', color: isSelected ? '#047857' : '#666', margin: '6px 0' }}>{plan.description}</p>}
                            <button
                              className={`customer-submit ${isSelected ? 'green-btn' : 'red-btn'}`}
                              style={{ marginTop: '10px', width: '100%', backgroundColor: isSelected ? '#10B981' : (isAnyPlanSelected ? '#9CA3AF' : undefined), opacity: (!isSelected && isAnyPlanSelected) ? 0.6 : 1, cursor: isAnyPlanSelected ? 'default' : 'pointer' }}
                              onClick={() => !isAnyPlanSelected && (plan.addon_id ? activateAddon(plan) : selectPlan(plan))}
                              disabled={busy || isAnyPlanSelected}
                            >
                              {isSelected ? 'Selected ✓' : (plan.addon_id ? 'Activate Add-on' : (isExisting ? 'Upgrade Plan' : 'Select & Book'))} <ChevronRight size={13} />
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            );
          });

          return (
            <>
              {renderedMessages}

            </>
          );
        })()}

        {!messages.some((m) => m.plans && m.plans.length > 0) && !state.selected_plan && availablePlans.length > 0 && (
          <div className="chat-card-section" style={{ margin: '15px 0' }}>
            <div style={{ fontSize: '12px', fontWeight: '700', color: '#E31B23', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Sparkles size={14} />
              {availablePlans[0]?.addon_id ? 'Available Add-on Services' : (isExisting ? 'Available Plan Upgrades' : 'Available Plans for Your Region')}
              {state.pincode && (
                <span style={{ marginLeft: 'auto', background: '#FFF0F1', color: '#E31B23', padding: '3px 8px', borderRadius: '12px', fontSize: '11px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <MapPin size={12} /> Pincode {state.pincode}
                </span>
              )}
            </div>
            <div className="plan-card-grid">
              {availablePlans.map((plan) => (
                <div className="wizard-plan" key={plan.plan_id || plan.addon_id} style={{ textAlign: 'left' }}>
                  <div className="plan-card-head">
                    <span>{plan.addon_id ? 'ADD-ON' : (plan.type || 'FIBER')}</span>
                    {plan.addon_id ? <Zap size={13} /> : <Wifi size={13} />}
                  </div>
                  <strong>{plan.name}</strong>
                  {plan.speed_mbps && <div className="wizard-speed">{plan.speed_mbps} Mbps</div>}
                  <div className="wizard-price">₹{plan.price_inr}<small>/month</small></div>
                  {plan.description && <p style={{ fontSize: '11px', color: '#666', margin: '6px 0' }}>{plan.description}</p>}
                  <button
                    className="customer-submit red-btn"
                    style={{ marginTop: '10px', width: '100%' }}
                    onClick={() => plan.addon_id ? activateAddon(plan) : selectPlan(plan)}
                    disabled={busy}
                  >
                    {plan.addon_id ? 'Activate Add-on' : (isExisting ? 'Upgrade Plan' : 'Select & Book')} <ChevronRight size={13} />
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
              <button className="wizard-button" style={{ background: '#3399cc', color: '#fff', border: 'none' }} onClick={confirmBookingAndPayment} disabled={busy}>
                Pay Now <Check size={16} style={{ marginLeft: '4px' }} />
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
          placeholder={isExisting ? "Type your Name, Email, Phone number, or plan upgrade / add-on request..." : "Type your message..."}
          disabled={busy}
        />
        <button className="red-btn" disabled={busy || !input.trim()}><Send size={16} /></button>
      </form>
    </main>
  )
}
