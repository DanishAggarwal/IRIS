import React from 'react'
import {
  ExternalLink,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  RotateCcw,
  Check,
  XCircle,
  FileDown,
  Info,
  Calendar,
  AlertTriangle,
  Loader2,
} from 'lucide-react'
import type { DiscoveredDocument } from '../../types/api'

interface DocumentTableProps {
  documents: DiscoveredDocument[]
  selectedIds: string[]
  onToggleSelect: (id: string) => void
  onToggleSelectAll: () => void
  onApproveAndIngestSingle: (doc: DiscoveredDocument) => void
  onRejectSingle: (doc: DiscoveredDocument) => void
  onReconsiderSingle: (doc: DiscoveredDocument) => void
  onRetrySingle: (doc: DiscoveredDocument) => void
  onViewDetails: (doc: DiscoveredDocument) => void
  currentPage: number
  totalPages: number
  totalItems: number
  pageSize: number
  onPageChange: (page: number) => void
  onPageSizeChange: (pageSize: number) => void
  isLoading: boolean
}

export const DocumentTable: React.FC<DocumentTableProps> = ({
  documents,
  selectedIds,
  onToggleSelect,
  onToggleSelectAll,
  onApproveAndIngestSingle,
  onRejectSingle,
  onReconsiderSingle,
  onRetrySingle,
  onViewDetails,
  currentPage,
  totalPages,
  totalItems,
  pageSize,
  onPageChange,
  onPageSizeChange,
  isLoading,
}) => {
  const allSelected =
    documents.length > 0 && documents.every((doc) => selectedIds.includes(doc.id))
  const someSelected =
    documents.some((doc) => selectedIds.includes(doc.id)) && !allSelected

  const formatDate = (isoString?: string | null) => {
    if (!isoString) return '—'
    try {
      return new Date(isoString).toLocaleDateString('en-IN', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    } catch {
      return isoString
    }
  }

  const renderStatusBadge = (status: string) => {
    switch (status) {
      case 'ingested':
        return (
          <span className="iris-badge-status iris-status-ingested">
            <Check size={11} className="mr-0.5 inline" /> Ingested
          </span>
        )
      case 'ingesting':
        return (
          <span className="iris-badge-status iris-status-ingesting">
            <Loader2 size={11} className="mr-0.5 inline iris-spinner" /> Ingesting...
          </span>
        )
      case 'downloading':
        return (
          <span className="iris-badge-status iris-status-downloading">
            <Loader2 size={11} className="mr-0.5 inline iris-spinner" /> Downloading...
          </span>
        )
      case 'approved':
        return (
          <span className="iris-badge-status iris-status-approved">
            Approved
          </span>
        )
      case 'rejected':
        return (
          <span className="iris-badge-status iris-status-rejected">
            <XCircle size={11} className="mr-0.5 inline" /> Rejected
          </span>
        )
      case 'download_failed':
        return (
          <span className="iris-badge-status iris-status-failed" title="Download failed">
            <AlertTriangle size={11} className="mr-0.5 inline" /> Download Failed
          </span>
        )
      case 'ingest_failed':
        return (
          <span className="iris-badge-status iris-status-failed" title="Ingestion failed">
            <AlertTriangle size={11} className="mr-0.5 inline" /> Ingest Failed
          </span>
        )
      case 'discovered':
      default:
        return (
          <span className="iris-badge-status iris-status-discovered">
            Discovered
          </span>
        )
    }
  }

  const renderChangeBadge = (changeStatus: string) => {
    if (changeStatus === 'potentially_changed') {
      return (
        <span
          className="iris-badge-change iris-change-potentially_changed"
          title="Remote content or ETag changed since initial scan"
        >
          <AlertTriangle size={11} className="mr-0.5 inline" /> Changed
        </span>
      )
    }
    if (changeStatus === 'unchanged') {
      return (
        <span className="iris-badge-change iris-change-unchanged">
          Unchanged
        </span>
      )
    }
    return (
      <span className="iris-badge-change iris-change-unknown">
        Unknown
      </span>
    )
  }

  const startItem = totalItems === 0 ? 0 : (currentPage - 1) * pageSize + 1
  const endItem = Math.min(currentPage * pageSize, totalItems)

  return (
    <div className="iris-crawler-table-card">
      <div className="iris-crawler-table-wrapper">
        <table className="iris-crawler-table">
          <thead>
            <tr>
              <th className="iris-th-select">
                <input
                  type="checkbox"
                  checked={allSelected}
                  ref={(input) => {
                    if (input) input.indeterminate = someSelected
                  }}
                  onChange={onToggleSelectAll}
                  aria-label="Select all documents on current page"
                />
              </th>
              <th className="iris-th-title">Document &amp; Metadata</th>
              <th className="iris-th-category">Source &amp; Category</th>
              <th className="iris-th-status">Lifecycle Status</th>
              <th className="iris-th-change">Change Detection</th>
              <th className="iris-th-dates">Timeline</th>
              <th className="iris-th-actions">Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={7} className="iris-table-loading-cell">
                  <Loader2 size={24} className="iris-spinner text-blue-600 mb-2" />
                  <p className="text-xs text-slate-500">Loading document catalogue...</p>
                </td>
              </tr>
            ) : documents.length === 0 ? (
              <tr>
                <td colSpan={7} className="iris-table-empty-cell">
                  <p className="font-semibold text-slate-700">No documents found matching filters</p>
                  <p className="text-xs text-slate-500 mt-1">
                    Try adjusting search parameters or click &ldquo;Scan Sources&rdquo; to discover PEC documents.
                  </p>
                </td>
              </tr>
            ) : (
              documents.map((doc) => {
                const isSelected = selectedIds.includes(doc.id)
                const isFailed = doc.status === 'download_failed' || doc.status === 'ingest_failed'
                const isActive = doc.status === 'downloading' || doc.status === 'ingesting'

                return (
                  <tr
                    key={doc.id}
                    className={`iris-table-row ${isSelected ? 'iris-row-selected' : ''}`}
                  >
                    <td className="iris-td-select">
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => onToggleSelect(doc.id)}
                        aria-label={`Select ${doc.title}`}
                      />
                    </td>

                    <td className="iris-td-title">
                      <div className="iris-doc-title-group">
                        <button
                          type="button"
                          className="iris-doc-title-btn"
                          onClick={() => onViewDetails(doc)}
                          title="Click to view metadata & audit history"
                        >
                          {doc.title}
                        </button>

                        <div className="iris-doc-submeta">
                          {doc.publication_date && (
                            <span className="iris-meta-pill" title="Publication Date">
                              <Calendar size={11} /> {doc.publication_date}
                            </span>
                          )}
                          {doc.meeting_number && (
                            <span className="iris-meta-pill" title="Senate Meeting Number">
                              Mtg #{doc.meeting_number}
                            </span>
                          )}
                          {doc.academic_year && (
                            <span className="iris-meta-pill" title="Academic Year">
                              AY {doc.academic_year}
                            </span>
                          )}
                          <a
                            href={doc.download_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="iris-doc-link-pdf"
                            title="Direct PDF link"
                          >
                            PDF <ExternalLink size={10} className="inline ml-0.5" />
                          </a>
                        </div>
                      </div>
                    </td>

                    <td className="iris-td-category">
                      <span className="iris-category-tag">{doc.category}</span>
                      <span className="iris-source-slug" title={doc.source_id}>
                        {doc.source_id}
                      </span>
                    </td>

                    <td className="iris-td-status">{renderStatusBadge(doc.status)}</td>

                    <td className="iris-td-change">{renderChangeBadge(doc.change_status)}</td>

                    <td className="iris-td-dates">
                      <div className="iris-dates-group">
                        <span className="text-xs text-slate-700">
                          Discovered: {formatDate(doc.first_discovered_at)}
                        </span>
                        {doc.ingested_at && (
                          <span className="text-xs text-emerald-700 font-medium">
                            Ingested: {formatDate(doc.ingested_at)}
                          </span>
                        )}
                      </div>
                    </td>

                    <td className="iris-td-actions">
                      <div className="iris-action-buttons-group">
                        {/* Primary Workflow Button */}
                        {doc.status !== 'ingested' && !isActive && !isFailed && doc.status !== 'rejected' && (
                          <button
                            type="button"
                            className="iris-btn-action-primary"
                            onClick={() => onApproveAndIngestSingle(doc)}
                            title="Approve and acquire document into IRIS"
                          >
                            <FileDown size={13} className="mr-1" />
                            <span>Approve &amp; Ingest</span>
                          </button>
                        )}

                        {/* Retry Button for Failed Acquisitions */}
                        {isFailed && (
                          <button
                            type="button"
                            className="iris-btn-action-retry"
                            onClick={() => onRetrySingle(doc)}
                            title="Retry download and ingestion"
                          >
                            <RefreshCw size={13} className="mr-1" />
                            <span>Retry</span>
                          </button>
                        )}

                        {/* Reject button for discovered or approved documents */}
                        {doc.status !== 'rejected' && doc.status !== 'ingested' && !isActive && (
                          <button
                            type="button"
                            className="iris-btn-action-reject"
                            onClick={() => onRejectSingle(doc)}
                            title="Mark document as rejected"
                            aria-label={`Reject ${doc.title}`}
                          >
                            <XCircle size={14} />
                          </button>
                        )}

                        {/* Reconsider button for rejected documents */}
                        {doc.status === 'rejected' && (
                          <button
                            type="button"
                            className="iris-btn-action-reconsider"
                            onClick={() => onReconsiderSingle(doc)}
                            title="Reconsider rejected document"
                          >
                            <RotateCcw size={13} className="mr-1" />
                            <span>Reconsider</span>
                          </button>
                        )}

                        {/* Details Modal Trigger */}
                        <button
                          type="button"
                          className="iris-btn-action-details"
                          onClick={() => onViewDetails(doc)}
                          title="View metadata and audit history"
                          aria-label={`Details for ${doc.title}`}
                        >
                          <Info size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Bar */}
      <div className="iris-crawler-pagination">
        <div className="iris-pagination-info">
          <span>
            Showing <strong>{startItem}</strong> &ndash; <strong>{endItem}</strong> of{' '}
            <strong>{totalItems}</strong> documents
          </span>
          <div className="iris-page-size-picker">
            <span className="text-xs text-slate-500">Per page:</span>
            <select
              value={pageSize}
              onChange={(e) => onPageSizeChange(Number(e.target.value))}
              className="iris-page-size-select"
              aria-label="Items per page"
            >
              <option value={10}>10</option>
              <option value={20}>20</option>
              <option value={50}>50</option>
            </select>
          </div>
        </div>

        <div className="iris-pagination-controls">
          <button
            type="button"
            className="iris-btn-page-nav"
            onClick={() => onPageChange(currentPage - 1)}
            disabled={currentPage <= 1 || isLoading}
            aria-label="Previous page"
          >
            <ChevronLeft size={16} />
          </button>

          <span className="iris-page-indicator">
            Page <strong>{currentPage}</strong> of <strong>{Math.max(1, totalPages)}</strong>
          </span>

          <button
            type="button"
            className="iris-btn-page-nav"
            onClick={() => onPageChange(currentPage + 1)}
            disabled={currentPage >= totalPages || isLoading}
            aria-label="Next page"
          >
            <ChevronRight size={16} />
          </button>
        </div>
      </div>
    </div>
  )
}
