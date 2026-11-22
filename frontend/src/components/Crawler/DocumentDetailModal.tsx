import React, { useEffect, useState } from 'react'
import {
  X,
  ExternalLink,
  Copy,
  Check,
  Calendar,
  Clock,
  FileCheck,
  AlertTriangle,
  History,
  FileText,
  Loader2,
} from 'lucide-react'
import type { DiscoveredDocument, DocumentAudit } from '../../types/api'
import { getDocumentHistory } from '../../services/api'

interface DocumentDetailModalProps {
  document: DiscoveredDocument | null
  onClose: () => void
}

export const DocumentDetailModal: React.FC<DocumentDetailModalProps> = ({
  document,
  onClose,
}) => {
  const [history, setHistory] = useState<DocumentAudit[]>([])
  const [isLoadingHistory, setIsLoadingHistory] = useState<boolean>(false)
  const [copiedSha, setCopiedSha] = useState<boolean>(false)

  useEffect(() => {
    if (!document) return

    let isMounted = true
    setIsLoadingHistory(true)

    getDocumentHistory(document.id)
      .then((records) => {
        if (isMounted) {
          setHistory(records)
          setIsLoadingHistory(false)
        }
      })
      .catch((err) => {
        console.error('Failed to load document audit history:', err)
        if (isMounted) {
          setIsLoadingHistory(false)
        }
      })

    return () => {
      isMounted = false
    }
  }, [document])

  if (!document) return null

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
    setCopiedSha(true)
    setTimeout(() => setCopiedSha(false), 2000)
  }

  const formatDate = (isoString?: string | null) => {
    if (!isoString) return '—'
    try {
      return new Date(isoString).toLocaleString('en-IN', {
        dateStyle: 'medium',
        timeStyle: 'short',
      })
    } catch {
      return isoString
    }
  }

  return (
    <div className="iris-modal-backdrop" onClick={onClose} role="dialog" aria-modal="true">
      <div className="iris-modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="iris-modal-header">
          <div className="iris-modal-title-group">
            <span className="iris-modal-badge-category">{document.category}</span>
            <h2 className="iris-modal-title">{document.title}</h2>
          </div>
          <button
            type="button"
            className="iris-modal-close-btn"
            onClick={onClose}
            aria-label="Close document details"
          >
            <X size={20} />
          </button>
        </div>

        <div className="iris-modal-body">
          {/* Status & Change Status Badges */}
          <div className="iris-modal-status-row">
            <div className="iris-modal-status-item">
              <span className="iris-modal-label">Lifecycle Status:</span>
              <span className={`iris-badge-status iris-status-${document.status}`}>
                {document.status}
              </span>
            </div>

            <div className="iris-modal-status-item">
              <span className="iris-modal-label">Change Signal:</span>
              <span className={`iris-badge-change iris-change-${document.change_status}`}>
                {document.change_status}
              </span>
            </div>

            {document.publication_date && (
              <div className="iris-modal-status-item">
                <span className="iris-modal-label">Published:</span>
                <span className="text-sm font-medium text-slate-700 flex items-center gap-1">
                  <Calendar size={13} /> {document.publication_date}
                </span>
              </div>
            )}
          </div>

          {/* Error Diagnostics if failed */}
          {document.error_message && (
            <div className="iris-modal-error-box">
              <AlertTriangle size={16} className="text-rose-600 flex-shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold text-rose-800 text-xs">Error Diagnostics:</span>
                <p className="text-xs text-rose-700 mt-0.5">{document.error_message}</p>
              </div>
            </div>
          )}

          {/* Rejection Reason if rejected */}
          {document.rejection_reason && (
            <div className="iris-modal-warning-box">
              <AlertTriangle size={16} className="text-amber-600 flex-shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold text-amber-900 text-xs">Rejection Note:</span>
                <p className="text-xs text-amber-800 mt-0.5">{document.rejection_reason}</p>
              </div>
            </div>
          )}

          {/* URLs & Identifiers */}
          <div className="iris-modal-section">
            <h3 className="iris-modal-section-title">URLs &amp; Verification</h3>
            <div className="iris-modal-meta-grid">
              <div className="iris-meta-cell">
                <span className="iris-meta-label">Source Webpage</span>
                <a
                  href={document.source_page_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="iris-meta-link"
                >
                  <span className="truncate">{document.source_page_url}</span>
                  <ExternalLink size={12} className="flex-shrink-0" />
                </a>
              </div>

              <div className="iris-meta-cell">
                <span className="iris-meta-label">PDF Direct Download URL</span>
                <a
                  href={document.download_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="iris-meta-link"
                >
                  <span className="truncate">{document.download_url}</span>
                  <ExternalLink size={12} className="flex-shrink-0" />
                </a>
              </div>

              {document.sha256 && (
                <div className="iris-meta-cell iris-meta-cell-full">
                  <span className="iris-meta-label">SHA-256 Hash</span>
                  <div className="iris-hash-box">
                    <code className="text-xs font-mono">{document.sha256}</code>
                    <button
                      type="button"
                      className="iris-btn-copy-hash"
                      onClick={() => copyToClipboard(document.sha256!)}
                      title="Copy SHA-256"
                    >
                      {copiedSha ? <Check size={13} className="text-emerald-600" /> : <Copy size={13} />}
                    </button>
                  </div>
                </div>
              )}

              {document.local_filename && (
                <div className="iris-meta-cell">
                  <span className="iris-meta-label">Local Acquired Filename</span>
                  <span className="text-xs font-mono text-slate-800 bg-slate-100 px-2 py-1 rounded inline-flex items-center gap-1">
                    <FileText size={12} /> {document.local_filename}
                  </span>
                </div>
              )}

              {document.ingested_document_id && (
                <div className="iris-meta-cell">
                  <span className="iris-meta-label">Linked IRIS Document ID</span>
                  <span className="text-xs font-mono text-slate-800 bg-slate-100 px-2 py-1 rounded inline-flex items-center gap-1">
                    <FileCheck size={12} className="text-emerald-600" /> {document.ingested_document_id}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Timestamps */}
          <div className="iris-modal-section">
            <h3 className="iris-modal-section-title">Timeline &amp; Discovery Metadata</h3>
            <div className="iris-modal-timestamps-grid">
              <div className="iris-timestamp-item">
                <Clock size={13} className="text-slate-400" />
                <div>
                  <span className="iris-ts-label">First Discovered</span>
                  <span className="iris-ts-val">{formatDate(document.first_discovered_at)}</span>
                </div>
              </div>

              <div className="iris-timestamp-item">
                <Clock size={13} className="text-slate-400" />
                <div>
                  <span className="iris-ts-label">Last Scanned</span>
                  <span className="iris-ts-val">{formatDate(document.last_scanned_at)}</span>
                </div>
              </div>

              <div className="iris-timestamp-item">
                <Clock size={13} className="text-slate-400" />
                <div>
                  <span className="iris-ts-label">Downloaded</span>
                  <span className="iris-ts-val">{formatDate(document.downloaded_at)}</span>
                </div>
              </div>

              <div className="iris-timestamp-item">
                <Clock size={13} className="text-slate-400" />
                <div>
                  <span className="iris-ts-label">Ingested in RAG</span>
                  <span className="iris-ts-val">{formatDate(document.ingested_at)}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Audit History Timeline */}
          <div className="iris-modal-section">
            <div className="flex items-center justify-between mb-2">
              <h3 className="iris-modal-section-title flex items-center gap-1.5 mb-0">
                <History size={15} /> Approval &amp; Ingestion Audit Trail
              </h3>
              <span className="text-xs text-slate-500 font-medium">
                {history.length} {history.length === 1 ? 'event' : 'events'} recorded
              </span>
            </div>

            {isLoadingHistory ? (
              <div className="iris-history-loading">
                <Loader2 size={18} className="iris-spinner text-blue-600 mr-2" />
                <span className="text-xs text-slate-500">Loading audit events...</span>
              </div>
            ) : history.length === 0 ? (
              <div className="iris-history-empty">
                <span className="text-xs text-slate-400">No decisions or transitions recorded yet.</span>
              </div>
            ) : (
              <div className="iris-audit-timeline">
                {history.map((record) => (
                  <div key={record.id} className="iris-audit-timeline-item">
                    <div className="iris-audit-marker" />
                    <div className="iris-audit-content">
                      <div className="iris-audit-top-row">
                        <span className="iris-audit-action">{record.action.toUpperCase()}</span>
                        <span className="iris-audit-time">{formatDate(record.created_at)}</span>
                      </div>
                      <div className="iris-audit-transition">
                        <span className="iris-audit-badge">{record.previous_status}</span>
                        <span className="text-slate-400">&rarr;</span>
                        <span className="iris-audit-badge">{record.new_status}</span>
                        <span className="iris-audit-admin">by {record.admin_email}</span>
                      </div>
                      {record.reason && (
                        <p className="iris-audit-reason">&ldquo;{record.reason}&rdquo;</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="iris-modal-footer">
          <button type="button" className="iris-btn-modal-close" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
