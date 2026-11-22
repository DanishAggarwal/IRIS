import React from 'react'
import { CheckCheck, X, Loader2, AlertCircle } from 'lucide-react'

interface BulkActionBarProps {
  selectedCount: number
  isProcessing: boolean
  processingMessage?: string | null
  error?: string | null
  onApproveAndIngest: () => void
  onClearSelection: () => void
}

export const BulkActionBar: React.FC<BulkActionBarProps> = ({
  selectedCount,
  isProcessing,
  processingMessage,
  error,
  onApproveAndIngest,
  onClearSelection,
}) => {
  if (selectedCount === 0) return null

  return (
    <div
      className="iris-crawler-bulk-bar iris-bulk-bar-active"
      role="region"
      aria-label="Bulk actions"
    >
      <div className="iris-bulk-left">
        <span className="iris-bulk-label font-medium">
          {selectedCount} {selectedCount === 1 ? 'document selected' : 'documents selected'}
        </span>

        {isProcessing && (
          <span className="iris-bulk-processing">
            <Loader2 size={14} className="iris-spinner text-blue-400 mr-1.5" />
            {processingMessage || 'Processing acquisition...'}
          </span>
        )}

        {error && (
          <span className="iris-bulk-error text-rose-400 text-xs flex items-center gap-1">
            <AlertCircle size={14} /> {error}
          </span>
        )}
      </div>

      <div className="iris-bulk-actions">
        <button
          type="button"
          className="iris-btn-bulk-approve"
          onClick={onApproveAndIngest}
          disabled={isProcessing}
        >
          {isProcessing ? (
            <>
              <Loader2 size={14} className="iris-spinner" />
              <span>Acquiring...</span>
            </>
          ) : (
            <>
              <CheckCheck size={16} />
              <span>Approve &amp; Ingest Selected</span>
            </>
          )}
        </button>

        <button
          type="button"
          className="iris-btn-bulk-clear"
          onClick={onClearSelection}
          disabled={isProcessing}
          title="Deselect all"
        >
          <X size={14} className="mr-1" />
          <span>Clear</span>
        </button>
      </div>
    </div>
  )
}
