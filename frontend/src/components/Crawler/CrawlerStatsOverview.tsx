import React from 'react'
import {
  FileText,
  CheckCircle2,
  Database,
  AlertTriangle,
  RefreshCw,
  Clock,
  AlertCircle,
} from 'lucide-react'
import type { CrawlerScan } from '../../types/api'

interface CrawlerStatsOverviewProps {
  stats: Record<string, number>
  latestScan: CrawlerScan | null
  isScanning: boolean
  activeStatusFilter?: string
  activeChangeFilter?: string
  onSelectStatus?: (status: string) => void
  onSelectChangeStatus?: (changeStatus: string) => void
}

export const CrawlerStatsOverview: React.FC<CrawlerStatsOverviewProps> = ({
  stats,
  latestScan,
  isScanning,
  activeStatusFilter = '',
  activeChangeFilter = '',
  onSelectStatus,
  onSelectChangeStatus,
}) => {
  const total = stats.total || 0
  const approved = stats.approved || 0
  const ingested = stats.ingested || 0
  const potentiallyChanged = stats.potentially_changed || 0
  const failed = (stats.download_failed || 0) + (stats.ingest_failed || 0)

  const handleCardClick = (type: 'total' | 'approved' | 'ingested' | 'changed' | 'failed') => {
    if (!onSelectStatus || !onSelectChangeStatus) return

    if (type === 'total') {
      onSelectStatus('')
      onSelectChangeStatus('')
    } else if (type === 'approved') {
      onSelectChangeStatus('')
      onSelectStatus(activeStatusFilter === 'approved' ? '' : 'approved')
    } else if (type === 'ingested') {
      onSelectChangeStatus('')
      onSelectStatus(activeStatusFilter === 'ingested' ? '' : 'ingested')
    } else if (type === 'changed') {
      onSelectStatus('')
      onSelectChangeStatus(activeChangeFilter === 'potentially_changed' ? '' : 'potentially_changed')
    } else if (type === 'failed') {
      onSelectChangeStatus('')
      onSelectStatus(activeStatusFilter === 'download_failed' || activeStatusFilter === 'ingest_failed' ? '' : 'download_failed')
    }
  }

  return (
    <div className="iris-crawler-stats-grid">
      <div
        className={`iris-crawler-stat-card ${onSelectStatus ? 'iris-stat-card-clickable' : ''} ${
          !activeStatusFilter && !activeChangeFilter ? 'iris-stat-card-active' : ''
        }`}
        onClick={() => handleCardClick('total')}
        title="View all discovered documents"
      >
        <div className="iris-crawler-stat-icon text-slate-600 bg-slate-100">
          <FileText size={20} />
        </div>
        <div className="iris-crawler-stat-content">
          <span className="iris-crawler-stat-label">Total Catalogue</span>
          <span className="iris-crawler-stat-value">{total}</span>
        </div>
      </div>

      <div
        className={`iris-crawler-stat-card ${onSelectStatus ? 'iris-stat-card-clickable' : ''} ${
          activeStatusFilter === 'approved' ? 'iris-stat-card-active' : ''
        }`}
        onClick={() => handleCardClick('approved')}
        title="Filter by Approved documents"
      >
        <div className="iris-crawler-stat-icon text-blue-600 bg-blue-50">
          <CheckCircle2 size={20} />
        </div>
        <div className="iris-crawler-stat-content">
          <span className="iris-crawler-stat-label">Approved</span>
          <span className="iris-crawler-stat-value">{approved}</span>
        </div>
      </div>

      <div
        className={`iris-crawler-stat-card ${onSelectStatus ? 'iris-stat-card-clickable' : ''} ${
          activeStatusFilter === 'ingested' ? 'iris-stat-card-active' : ''
        }`}
        onClick={() => handleCardClick('ingested')}
        title="Filter by Ingested in RAG documents"
      >
        <div className="iris-crawler-stat-icon text-emerald-600 bg-emerald-50">
          <Database size={20} />
        </div>
        <div className="iris-crawler-stat-content">
          <span className="iris-crawler-stat-label">Ingested in RAG</span>
          <span className="iris-crawler-stat-value">{ingested}</span>
        </div>
      </div>

      <div
        className={`iris-crawler-stat-card ${onSelectChangeStatus ? 'iris-stat-card-clickable' : ''} ${
          activeChangeFilter === 'potentially_changed' ? 'iris-stat-card-active' : ''
        }`}
        onClick={() => handleCardClick('changed')}
        title="Filter by Potentially Changed documents"
      >
        <div className="iris-crawler-stat-icon text-amber-600 bg-amber-50">
          <AlertTriangle size={20} />
        </div>
        <div className="iris-crawler-stat-content">
          <span className="iris-crawler-stat-label">Potentially Changed</span>
          <span className="iris-crawler-stat-value">{potentiallyChanged}</span>
        </div>
      </div>

      <div
        className={`iris-crawler-stat-card ${onSelectStatus ? 'iris-stat-card-clickable' : ''} ${
          activeStatusFilter === 'download_failed' || activeStatusFilter === 'ingest_failed' ? 'iris-stat-card-active' : ''
        }`}
        onClick={() => handleCardClick('failed')}
        title="Filter by Failed acquisitions"
      >
        <div className="iris-crawler-stat-icon text-rose-600 bg-rose-50">
          <AlertCircle size={20} />
        </div>
        <div className="iris-crawler-stat-content">
          <span className="iris-crawler-stat-label">Failed Acquisitions</span>
          <span className="iris-crawler-stat-value">{failed}</span>
        </div>
      </div>

      <div className="iris-crawler-stat-card iris-crawler-stat-card-scan">
        <div className="iris-crawler-stat-icon text-indigo-600 bg-indigo-50">
          <RefreshCw size={20} className={isScanning ? 'iris-spinner' : ''} />
        </div>
        <div className="iris-crawler-stat-content">
          <span className="iris-crawler-stat-label">Latest Discovery Scan</span>
          <div className="iris-crawler-scan-summary">
            {isScanning ? (
              <span className="text-amber-600 font-semibold text-xs flex items-center gap-1">
                <Clock size={12} className="iris-spinner" /> Scanning PEC sources...
              </span>
            ) : latestScan ? (
              <span className="text-xs text-slate-700">
                <span className={`iris-scan-status-dot iris-scan-${latestScan.status}`} />
                {latestScan.status === 'completed'
                  ? `Completed (${latestScan.new_documents} new)`
                  : latestScan.status === 'failed'
                  ? 'Failed'
                  : 'Running'}
              </span>
            ) : (
              <span className="text-xs text-slate-400">No scans recorded yet</span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
