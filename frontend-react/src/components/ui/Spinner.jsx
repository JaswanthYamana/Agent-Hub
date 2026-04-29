import React from 'react'

export function Spinner({ size = '' }) {
  return <div className={`spinner ${size === 'lg' ? 'spinner-lg' : size === 'sm' ? 'spinner-sm' : ''}`} />
}

export function LoadingRow({ text = 'Loading…' }) {
  return (
    <div className="loading-row">
      <Spinner />
      <span>{text}</span>
    </div>
  )
}
