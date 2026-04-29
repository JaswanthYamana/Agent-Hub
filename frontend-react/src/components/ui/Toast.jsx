import React, { useEffect, useState } from 'react'
import { useStore } from '../../store/useStore'

function Toast({ id, message, type }) {
  const [show, setShow] = useState(false)
  const dismiss = useStore((s) => s.dismissToast)

  useEffect(() => {
    const t = requestAnimationFrame(() => setShow(true))
    return () => cancelAnimationFrame(t)
  }, [])

  return (
    <div
      className={`toast toast-${type} ${show ? 'show' : ''}`}
      onClick={() => dismiss(id)}
      title="Click to dismiss"
    >
      <span style={{ flex: 1 }}>{message}</span>
    </div>
  )
}

export function ToastContainer() {
  const toasts = useStore((s) => s.toasts)
  return (
    <div className="toast-container">
      {toasts.map((t) => (
        <Toast key={t.id} {...t} />
      ))}
    </div>
  )
}
