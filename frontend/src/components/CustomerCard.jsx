import React from 'react'
import { Wifi, UserRound, CheckCircle2, ChevronRight, Pencil } from 'lucide-react'

export function SavedCustomerCard({ custName, custPhone, custEmail, onSave, busy }) {
  const [isEditing, setIsEditing] = React.useState(false)
  const [editForm, setEditForm] = React.useState({ name: custName, phone: custPhone, email: custEmail })
  const [err, setErr] = React.useState('')

  React.useEffect(() => {
    setEditForm({ name: custName, phone: custPhone, email: custEmail })
  }, [custName, custPhone, custEmail])

  const handleSave = (e) => {
    e.preventDefault()
    if (!editForm.name.trim() || !/^\d{10}$/.test(editForm.phone) || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(editForm.email)) {
      setErr('Please enter a valid name, 10-digit phone number, and email.')
      return
    }
    setErr('')
    setIsEditing(false)
    if (onSave) {
      onSave(editForm)
    }
  }

  if (isEditing) {
    return (
      <div className="other-message assistant" style={{ marginTop: '12px' }}>
        <span><Wifi size={14} /></span>
        <div className="message-content" style={{ width: '100%', maxWidth: '540px', padding: '16px', background: '#FFFFFF', border: '2px solid #10B981', borderRadius: '14px', boxShadow: '0 4px 12px rgba(16, 185, 129, 0.12)', boxSizing: 'border-box' }}>
          <div className="customer-form-title" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', color: '#059669', fontSize: '13px', fontWeight: '700', marginBottom: '8px' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <UserRound size={15} style={{ color: '#10B981' }} /> Edit Saved Details
            </span>
            <button
              type="button"
              onClick={() => setIsEditing(false)}
              style={{ background: 'transparent', border: 'none', color: '#6b7280', fontSize: '11px', fontWeight: '600', cursor: 'pointer' }}
            >
              Cancel
            </button>
          </div>
          {err && <p style={{ color: '#dc2626', fontSize: '11px', margin: '0 0 8px', fontWeight: '600' }}>{err}</p>}
          <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ fontSize: '11px', fontWeight: '700', color: '#374151' }}>Name</label>
              <input
                value={editForm.name}
                onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                placeholder="Full name"
                required
                style={{ width: '100%', border: '1px solid #a7f3d0', borderRadius: '10px', padding: '9px 12px', fontSize: '12px', outline: 'none', boxSizing: 'border-box' }}
              />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ fontSize: '11px', fontWeight: '700', color: '#374151' }}>Phone</label>
              <input
                value={editForm.phone}
                onChange={(e) => setEditForm({ ...editForm, phone: e.target.value.replace(/\D/g, '').slice(0, 10) })}
                placeholder="10-digit mobile number"
                inputMode="numeric"
                required
                style={{ width: '100%', border: '1px solid #a7f3d0', borderRadius: '10px', padding: '9px 12px', fontSize: '12px', outline: 'none', boxSizing: 'border-box' }}
              />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ fontSize: '11px', fontWeight: '700', color: '#374151' }}>Email</label>
              <input
                value={editForm.email}
                onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
                placeholder="email@example.com"
                type="email"
                required
                style={{ width: '100%', border: '1px solid #a7f3d0', borderRadius: '10px', padding: '9px 12px', fontSize: '12px', outline: 'none', boxSizing: 'border-box' }}
              />
            </div>
            <button
              type="submit"
              disabled={busy}
              style={{
                width: '100%',
                marginTop: '6px',
                padding: '10px 14px',
                borderRadius: '10px',
                fontWeight: '700',
                fontSize: '12px',
                cursor: 'pointer',
                background: '#10B981',
                color: '#FFFFFF',
                border: 'none',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '6px'
              }}
            >
              Update Details <CheckCircle2 size={14} />
            </button>
          </form>
        </div>
      </div>
    )
  }

  return (
    <div className="other-message assistant" style={{ marginTop: '12px' }}>
      <span><Wifi size={14} /></span>
      <div className="message-content" style={{ width: '100%', maxWidth: '540px', padding: '16px', background: '#ECFDF5', border: '2px solid #10B981', borderRadius: '14px', boxShadow: '0 4px 12px rgba(16, 185, 129, 0.08)', boxSizing: 'border-box' }}>
        <div className="customer-form-title" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', color: '#059669', fontSize: '13px', fontWeight: '700', marginBottom: '6px' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <UserRound size={15} style={{ color: '#10B981' }} /> Customer Details
          </span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ background: '#D1FAE5', color: '#047857', padding: '3px 10px', borderRadius: '12px', fontSize: '10px', fontWeight: '700', display: 'flex', alignItems: 'center', gap: '4px' }}>
              <CheckCircle2 size={13} /> Saved ✓
            </span>
            <button
              type="button"
              onClick={() => setIsEditing(true)}
              style={{
                background: '#FFFFFF',
                color: '#059669',
                border: '1px solid #10B981',
                borderRadius: '10px',
                padding: '3px 9px',
                fontSize: '11px',
                fontWeight: '700',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                boxShadow: '0 1px 3px rgba(0,0,0,0.05)'
              }}
            >
              <Pencil size={11} /> Edit
            </button>
          </div>
        </div>
        <p style={{ margin: '2px 0 10px', color: '#047857', fontSize: '11px' }}>Your contact information has been verified and recorded.</p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#FFFFFF', padding: '8px 12px', borderRadius: '8px', border: '1px solid #A7F3D0' }}>
            <span style={{ fontSize: '11px', color: '#059669', fontWeight: '700' }}>Name:</span>
            <strong style={{ fontSize: '12px', color: '#065F46' }}>{editForm.name}</strong>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#FFFFFF', padding: '8px 12px', borderRadius: '8px', border: '1px solid #A7F3D0' }}>
            <span style={{ fontSize: '11px', color: '#059669', fontWeight: '700' }}>Phone:</span>
            <strong style={{ fontSize: '12px', color: '#065F46' }}>{editForm.phone}</strong>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#FFFFFF', padding: '8px 12px', borderRadius: '8px', border: '1px solid #A7F3D0' }}>
            <span style={{ fontSize: '11px', color: '#059669', fontWeight: '700' }}>Email:</span>
            <strong style={{ fontSize: '12px', color: '#065F46', wordBreak: 'break-all' }}>{editForm.email}</strong>
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
      <div className="message-content" style={{ width: '100%', maxWidth: '540px', padding: '16px', background: '#FFFFFF', border: '2px solid #E31B23', borderRadius: '14px', boxShadow: '0 4px 12px rgba(227, 27, 35, 0.08)', boxSizing: 'border-box' }}>
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

