import React from 'react'
import { AlertCircle, CheckCircle2, Clock, X } from 'lucide-react'
import type { CrawlerScan } from '../../types/api'

interface ScanProgressBannerProps {
  scan: CrawlerScan | null
  isScanning: boolean
  onDismiss?: () => void
}

export const ScanProgressBanner: React.FC<ScanProgressBannerProps> = ({
  scan,
  isScanning,
  onDismiss,
}) => {
  if (isScanning) {
    return (
      <div className="iris-crawler-scan-banner iris-scan-banner-running" role="status">
        <div className="iris-scan-banner-left">
          <Clock size={16} className="iris-spinner text-amber-600 flex-shrink-0" />
          <span className="text-xs font-medium text-amber-900">
            Discovery scan in progress: scanning enabled PEC institutional sources...
          </span>
        </div>
      </div>
    )
  }

  if (!scan) return null

  if (scan.status === 'failed') {
    return (
      <div className="iris-crawler-scan-banner iris-scan-banner-failed" role="alert">
        <div className="iris-scan-banner-left">
          <AlertCircle size={16} className="text-rose-600 flex-shrink-0" />
          <span className="text-xs text-rose-800">
            <strong>Scan error:</strong> {scan.error_message || 'One or more institutional sources could not be scanned.'}
          </span>
        </div>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            className="iris-scan-banner-close"
            aria-label="Dismiss banner"
          >
            <X size={14} />
          </button>
        )}
      </div>
    )
  }

  if (scan.status === 'completed') {
    return (
      <div className="iris-crawler-scan-banner iris-scan-banner-completed" role="status">
        <div className="iris-scan-banner-left">
          <CheckCircle2 size={16} className="text-emerald-600 flex-shrink-0" />
          <span className="text-xs text-emerald-800">
            <strong>Scan completed:</strong> Discovered {scan.total_discovered} documents across {scan.total_sources} sources (
            <strong>{scan.new_documents} new</strong>, {scan.updated_documents} updated, {scan.potentially_changed} changed).
          </span>
        </div>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            className="iris-scan-banner-close"
            aria-label="Dismiss banner"
          >
            <X size={14} />
          </button>
        )}
      </div>
    )
  }

  return null
}
