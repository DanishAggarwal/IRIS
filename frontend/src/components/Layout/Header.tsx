import React from 'react'
import { Sparkles, RotateCcw } from 'lucide-react'
import { StatusBadge } from './StatusBadge'
import type { ConnectionStatus } from '../../types/chat'

interface HeaderProps {
  connectionStatus: ConnectionStatus
  hasMessages: boolean
  onResetChat?: () => void
}

export const Header: React.FC<HeaderProps> = ({
  connectionStatus,
  hasMessages,
  onResetChat,
}) => {
  return (
    <header className="iris-header">
      <div className="iris-header-content">
        <div className="iris-brand-group">
          <div className="iris-logo-mark" aria-hidden="true">
            <span className="iris-logo-text">IRIS</span>
            <Sparkles className="iris-sparkle-icon" size={14} />
          </div>
          <div className="iris-title-group">
            <div className="iris-main-title">
              <h1>Information Retrieval &amp; Intelligence System</h1>
              <span className="iris-badge-pec">PEC</span>
            </div>
            <p className="iris-subtitle">
              Your grounded institutional and academic information assistant
            </p>
          </div>
        </div>

        <div className="iris-header-actions">
          <StatusBadge status={connectionStatus} />

          {hasMessages && onResetChat && (
            <button
              type="button"
              onClick={onResetChat}
              className="iris-btn-reset"
              title="Start a new conversation"
              aria-label="Start a new conversation"
            >
              <RotateCcw size={15} />
              <span className="iris-reset-label">New Chat</span>
            </button>
          )}
        </div>
      </div>
    </header>
  )
}
