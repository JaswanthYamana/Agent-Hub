import React from 'react'

export function EmptyState({ icon = '📭', title, description, action }) {
  return (
    <div className="empty-state">
      <div className="empty-icon">{icon}</div>
      {title && <strong>{title}</strong>}
      {description && <p>{description}</p>}
      {action}
    </div>
  )
}
