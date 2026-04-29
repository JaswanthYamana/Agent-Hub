/** Shared formatting & classification utilities. */

export function short(str, max = 32) {
  if (!str) return ''
  return str.length > max ? str.slice(0, max) + '…' : str
}

export function fmtDuration(ms) {
  if (ms == null) return '—'
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

export function fmtTimestamp(unixSec) {
  if (!unixSec) return '—'
  return new Date(unixSec * 1000).toISOString().slice(0, 19).replace('T', ' ')
}

export function fmtTimeHMS(unixSec) {
  if (!unixSec) return ''
  return new Date(unixSec * 1000).toISOString().slice(11, 19)
}

export function statusCls(status) {
  const s = (status || '').toUpperCase()
  if (s === 'OK' || s === 'DONE') return 'ok'
  if (s === 'ERROR')              return 'error'
  if (s === 'ANOMALOUS')          return 'warn'
  return 'muted'
}

export function sevCls(sev) {
  const s = (sev || '').toLowerCase()
  if (s === 'critical') return 'critical'
  if (s === 'high')     return 'error'
  if (s === 'medium')   return 'warn'
  return 'ok'
}

export function pctColor(val) {
  if (val == null) return 'var(--text-secondary)'
  if (val >= 0.8) return 'var(--green)'
  if (val >= 0.5) return 'var(--orange)'
  return 'var(--red)'
}

export function scenarioCls(scenario) {
  return `sp-${(scenario || 'normal').replace(/_/g, '_')}`
}

export function kindColor(kind) {
  const k = (kind || '').toUpperCase()
  const map = {
    TOOL:       'var(--blue)',
    LLM:        'var(--purple)',
    AGENT:      'var(--green)',
    RETRIEVER:  'var(--teal)',
    CHAIN:      'var(--orange)',
    ERROR:      'var(--red)',
  }
  return map[k] || 'var(--text-muted)'
}
