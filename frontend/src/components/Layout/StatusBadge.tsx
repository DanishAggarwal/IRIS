import React from 'react'
import type { ConnectionStatus } from '../../types/chat'

interface StatusBadgeProps {
  status: ConnectionStatus
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status }) => {
  const config = {
    connected: {
      label: 'Connected',
      dotClass: 'bg-emerald-500',
      badgeClass: 'text-emerald-700 bg-emerald-50 border-emerald-200',
    },
    disconnected: {
      label: 'Disconnected',
      dotClass: 'bg-rose-500',
      badgeClass: 'text-rose-700 bg-rose-50 border-rose-200',
    },
    checking: {
      label: 'Checking...',
      dotClass: 'bg-amber-500 animate-pulse',
      badgeClass: 'text-amber-700 bg-amber-50 border-amber-200',
    },
  }[status]

  return (
    <div
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${config.badgeClass}`}
      role="status"
      aria-label={`Backend connection: ${config.label}`}
      title={`Backend connection: ${config.label}`}
    >
      <span className={`w-2 h-2 rounded-full ${config.dotClass}`} aria-hidden="true" />
      <span>{config.label}</span>
    </div>
  )
}
