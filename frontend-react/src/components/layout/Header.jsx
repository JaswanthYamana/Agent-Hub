import React from 'react'
import { useStore } from '../../store/useStore'

export function Header({ onShowShortcuts }) {
  const online = useStore((s) => s.backendOnline)

  const dotCls =
    online === true  ? 'status-dot online' :
    online === false ? 'status-dot offline' :
    'status-dot'

  const label =
    online === true  ? 'Backend Online' :
    online === false ? 'Backend Offline' :
    'Checking…'

  return (
    <header className="header">
      <div className="header-logo">
        <div className="header-logo-icon">⬡</div>
        <div>
          <div>AI Agent Flight Recorder</div>
          <div className="header-tagline">Agentic AI Reliability &amp; Red-Teaming Lab</div>
        </div>
      </div>

      <div className="header-spacer" />

      <div className="header-status">
        <span className={dotCls} />
        <span>{label}</span>
      </div>

      <button className="header-kbd-hint" onClick={onShowShortcuts} title="Keyboard shortcuts">
        ?
      </button>
    </header>
  )
}
