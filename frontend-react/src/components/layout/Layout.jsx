import React, { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Header } from './Header'
import { Sidebar } from './Sidebar'
import { ToastContainer } from '../ui/Toast'
import { KeyboardShortcutsModal } from '../ui/KeyboardShortcutsModal'
import { useKeyboard } from '../../hooks/useKeyboard'

export function Layout({ children }) {
  const navigate   = useNavigate()
  const [showShortcuts, setShowShortcuts] = useState(false)

  const handleDemoScenario = useCallback((scenario, task) => {
    navigate('/execute', { state: { scenario, task } })
  }, [navigate])

  // Global "g <key>" navigation shortcuts
  useKeyboard({
    'g d': () => navigate('/dashboard'),
    'g x': () => navigate('/execute'),
    'g t': () => navigate('/traces'),
    'g g': () => navigate('/graph'),
    'g m': () => navigate('/metrics'),
    'g a': () => navigate('/anomalies'),
    'g p': () => navigate('/replay'),
    'g r': () => navigate('/redteam'),
    'g i': () => navigate('/ingest'),
    'g c': () => navigate('/compare'),
    'g s': () => navigate('/settings'),
    '?':   () => setShowShortcuts(true),
    'Escape': () => setShowShortcuts(false),
  })

  return (
    <div className="app-root">
      <Header onShowShortcuts={() => setShowShortcuts(true)} />

      <div className="app-body">
        <Sidebar onDemoScenario={handleDemoScenario} />
        <main className="app-main">
          {children}
        </main>
      </div>

      <ToastContainer />

      {showShortcuts && (
        <KeyboardShortcutsModal onClose={() => setShowShortcuts(false)} />
      )}
    </div>
  )
}
