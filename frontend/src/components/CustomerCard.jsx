import React from 'react'
import { Wifi, UserRound, CheckCircle2, ChevronRight } from 'lucide-react'

export function SavedCustomerCard({ custName, custPhone, custEmail }) {
  return (
    <div className="other-message assistant" style={{ marginTop: '12px' }}>
      <span><Wifi size={14} /></span>
      <div className="message-content" style={{ maxWidth: '80%', width: '100%', padding: '14px 16px', background: '#ECFDF5', border: '2px solid #10B981', borderRadius: '14px', boxShadow: '0 4px 12px rgba(16, 185, 129, 0.08)' }}>
        <div className="customer-form-title" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', color: '#059669', fontSize: '13px', fontWeight: '700', marginBottom: '6px' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <UserRound size={15} style={{ color: '#10B981' }} /> Customer Details
          </span>
          <span style={{ background: '#D1FAE5', color: '#047857', padding: '3px 10px', borderRadius: '12px', fontSize: '10px', fontWeight: '700', display: 'flex', alignItems: 'center', gap: '4px' }}>
            <CheckCircle2 size={13} /> Saved ✓
          </span>
        </div>
        <p style={{ margin: '2px 0 10px', color: '#047857', fontSize: '11px' }}>Your contact information has been verified and recorded.</p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#FFFFFF', padding: '8px 12px', borderRadius: '8px', border: '1px solid #A7F3D0' }}>
            <span style={{ fontSize: '11px', color: '#059669', fontWeight: '700' }}>Name:</span>
            <strong style={{ fontSize: '12px', color: '#065F46' }}>{custName}</strong>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#FFFFFF', padding: '8px 12px', borderRadius: '8px', border: '1px solid #A7F3D0' }}>
            <span style={{ fontSize: '11px', color: '#059669', fontWeight: '700' }}>Phone:</span>
            <strong style={{ fontSize: '12px', color: '#065F46' }}>{custPhone}</strong>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#FFFFFF', padding: '8px 12px', borderRadius: '8px', border: '1px solid #A7F3D0' }}>
            <span style={{ fontSize: '11px', color: '#059669', fontWeight: '700' }}>Email:</span>
            <strong style={{ fontSize: '12px', color: '#065F46', wordBreak: 'break-all' }}>{custEmail}</strong>
          </div>
        </div>
      </div>
    </div>
  )
}

export function CustomerFormCard({ selectedPlanName, customer, setCustomer, submitCustomer, busy }) {
  return (
    <div className="other-message assistant" style={{ marginTop: '12px' }}>
      <span><Wifi size={14} /></span>
      <div className="message-content" style={{ maxWidth: '80%', width: '100%', padding: '16px', background: '#FFFFFF', border: '2px solid #E31B23', borderRadius: '14px', boxShadow: '0 4px 12px rgba(227, 27, 35, 0.08)' }}>
        <div className="customer-form-title" style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#B80E16', fontSize: '13px', fontWeight: '700', marginBottom: '4px' }}>
          <UserRound size={15} style={{ color: '#E31B23' }} /> Customer Details for {selectedPlanName}
        </div>
        <p style={{ margin: '4px 0 12px', color: '#6b7280', fontSize: '11px' }}>Please enter your contact details to proceed with installation scheduling.</p>
        <form onSubmit={submitCustomer} style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <label style={{ fontSize: '11px', fontWeight: '700', color: '#374151' }}>Name</label>
            <input
              value={customer.name}
              onChange={(e) => setCustomer({ ...customer, name: e.target.value })}
              placeholder="Full name"
              required
              style={{ width: '100%', border: '1px solid #e5e7eb', borderRadius: '10px', padding: '9px 12px', fontSize: '12px', outline: 'none', boxSizing: 'border-box' }}
            />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <label style={{ fontSize: '11px', fontWeight: '700', color: '#374151' }}>Phone</label>
            <input
              value={customer.phone}
              onChange={(e) => setCustomer({ ...customer, phone: e.target.value.replace(/\D/g, '').slice(0, 10) })}
              placeholder="10-digit mobile number"
              inputMode="numeric"
              required
              style={{ width: '100%', border: '1px solid #e5e7eb', borderRadius: '10px', padding: '9px 12px', fontSize: '12px', outline: 'none', boxSizing: 'border-box' }}
            />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <label style={{ fontSize: '11px', fontWeight: '700', color: '#374151' }}>Email</label>
            <input
              value={customer.email}
              onChange={(e) => setCustomer({ ...customer, email: e.target.value })}
              placeholder="email@example.com"
              type="email"
              required
              style={{ width: '100%', border: '1px solid #e5e7eb', borderRadius: '10px', padding: '9px 12px', fontSize: '12px', outline: 'none', boxSizing: 'border-box' }}
            />
          </div>
          <button className="customer-submit red-btn" disabled={busy} style={{ width: '100%', marginTop: '6px', padding: '10px 14px', borderRadius: '10px', fontWeight: '700', fontSize: '12px', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' }}>
            Save Details & Select Slot <ChevronRight size={14} />
          </button>
        </form>
      </div>
    </div>
  )
}
