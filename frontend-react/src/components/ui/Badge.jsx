import React from 'react'
import { sevCls, statusCls } from '../../utils/format'

export function Badge({ variant, children, className = '' }) {
  return (
    <span className={`badge badge-${variant} ${className}`}>
      {children}
    </span>
  )
}

export function StatusBadge({ success, label }) {
  const text = label ?? (success ? 'OK' : 'ERROR')
  return <Badge variant={success ? 'ok' : 'error'}>{text}</Badge>
}

export function SeverityBadge({ severity }) {
  return <Badge variant={sevCls(severity)}>{severity || '?'}</Badge>
}

export function ScenarioPill({ scenario }) {
  const s = scenario || 'normal'
  return (
    <span className={`scenario-pill sp-${s.replace(/-/g, '_')}`}>
      {s}
    </span>
  )
}

export function KindBadge({ kind }) {
  const k = (kind || 'TOOL').toUpperCase()
  const color = {
    TOOL:      'blue',
    LLM:       'purple',
    AGENT:     'ok',
    RETRIEVER: 'muted',
    CHAIN:     'warn',
  }[k] || 'muted'
  return <Badge variant={color}>{k}</Badge>
}

export function MethodBadge({ method }) {
  return (
    <span className={`method-badge ${(method || '').toLowerCase()}`}>
      {(method || '').toUpperCase()}
    </span>
  )
}
