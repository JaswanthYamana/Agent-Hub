import React from 'react'

const SHORTCUTS = [
  { keys: ['g', 'd'],       desc: 'Navigate to Dashboard' },
  { keys: ['g', 'x'],       desc: 'Navigate to Execute Agent' },
  { keys: ['g', 't'],       desc: 'Navigate to Trace Explorer' },
  { keys: ['g', 'g'],       desc: 'Navigate to Execution Graph' },
  { keys: ['g', 'm'],       desc: 'Navigate to Metrics' },
  { keys: ['g', 'a'],       desc: 'Navigate to Anomalies' },
  { keys: ['g', 'p'],       desc: 'Navigate to Replay Debugger' },
  { keys: ['g', 'r'],       desc: 'Navigate to Red-Team Lab' },
  { keys: ['g', 'i'],       desc: 'Navigate to Ingest / SDK' },
  { keys: ['g', 's'],       desc: 'Navigate to Settings' },
  { keys: ['←'],            desc: 'Replay: previous step' },
  { keys: ['→', 'Space'],   desc: 'Replay: next step' },
  { keys: ['?'],            desc: 'Show this help dialog' },
  { keys: ['Esc'],          desc: 'Close dialog / detail panel' },
]

export function KeyboardShortcutsModal({ onClose }) {
  return (
    <div className="kbd-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="kbd-modal">
        <div className="flex items-center justify-between mb-6">
          <h3>Keyboard Shortcuts</h3>
          <button className="btn-icon" onClick={onClose}>✕</button>
        </div>
        {SHORTCUTS.map(({ keys, desc }) => (
          <div key={desc} className="kbd-row">
            <span className="text-secondary" style={{ fontSize: 12 }}>{desc}</span>
            <span className="kbd">
              {keys.map((k) => <kbd key={k}>{k}</kbd>)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
