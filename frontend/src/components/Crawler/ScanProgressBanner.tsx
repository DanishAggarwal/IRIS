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
      <div className="iris-crawler-scan-banner iris-scan-banner-running">
        <div className="iris-scan-banner-left">
          <Clock size={18} className="iris-spinner text-amber-600" />
          <div>
            <strong>PEC Discovery Scan in Progress</strong>
            <p className="text-xs text-slate-600">
              Scanning enabled PEC institutional pages to discover syllabus, calendar, and Senate records...
            </p>
          </div>
        </div>
      </div>
    )
  }

  if (!scan) return null

  if (scan.status === 'failed') {
    return (
      <div className="iris-crawler-scan-banner iris-scan-banner-failed">
        <div className="iris-scan-banner-left">
          <AlertCircle size={18} className="text-rose-600 flex-shrink-0" />
          <div>
            <strong className="text-rose-800">Discovery Scan Encountered Errors</strong>
            <p className="text-xs text-rose-700">
              {scan.error_message || 'One or more institutional sources could not be scanned.'}
            </p>
          </div>
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
      <div className="iris-crawler-scan-banner iris-scan-banner-completed">
        <div className="iris-scan-banner-left">
          <CheckCircle2 size={18} className="text-emerald-600 flex-shrink-0" />
          <div>
            <strong className="text-emerald-900">Scan Completed Successfully</strong>
            <p className="text-xs text-emerald-800">
              Found {scan.total_discovered} documents across {scan.total_sources} sources (
              <strong>{scan.new_documents} new</strong>, {scan.updated_documents} updated,{' '}
              {scan.potentially_changed} potentially changed).
            </p>
          </div>
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
