import React from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'

interface ErrorCardProps {
  error: string
  retryQuery?: string
  onRetry?: (query: string) => void
}

export const ErrorCard: React.FC<ErrorCardProps> = ({ error, retryQuery, onRetry }) => {
  return (
    <div className="iris-card iris-error-card">
      <div className="iris-card-banner iris-banner-rose">
        <AlertTriangle size={17} className="iris-card-banner-icon text-rose-600" />
        <span className="iris-card-banner-title">Service Interruption</span>
      </div>

      <div className="iris-error-body">
        <p className="iris-error-message">{error}</p>

        {retryQuery && onRetry && (
          <div className="iris-error-actions">
            <button
              type="button"
              onClick={() => onRetry(retryQuery)}
              className="iris-btn-retry"
              aria-label="Retry sending your question"
            >
              <RefreshCw size={14} className="iris-retry-icon" />
              <span>Retry question</span>
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
