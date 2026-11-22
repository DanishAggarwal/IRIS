import React, { useCallback, useEffect, useRef, useState } from 'react'
import { ShieldAlert, AlertCircle, CheckCircle2 } from 'lucide-react'
import type {
  CrawlerScan,
  CrawlerSource,
  DiscoveredDocument,
  UserProfile,
} from '../../types/api'
import {
  approveDocument,
  getCrawlerStats,
  getDiscoveredDocument,
  getDocumentIngestionStatus,
  getLatestCrawlerScan,
  ingestDocument,
  listCrawlerSources,
  listDiscoveredDocuments,
  reconsiderDocument,
  rejectDocument,
  retryDocument,
  triggerCrawlerScan,
} from '../../services/api'
import { CrawlerStatsOverview } from './CrawlerStatsOverview'
import { CrawlerFilterBar } from './CrawlerFilterBar'
import { ScanProgressBanner } from './ScanProgressBanner'
import { BulkActionBar } from './BulkActionBar'
import { DocumentTable } from './DocumentTable'
import { DocumentDetailModal } from './DocumentDetailModal'

interface CrawlerAdminContainerProps {
  user: UserProfile | null
  onBackToChat?: () => void
}

export const CrawlerAdminContainer: React.FC<CrawlerAdminContainerProps> = ({
  user,
}) => {
  // Access check
  if (!user || user.role !== 'admin') {
    return (
      <div className="iris-crawler-access-denied">
        <div className="iris-card iris-card-access-denied">
          <ShieldAlert size={48} className="text-rose-600 mb-3" />
          <h2 className="text-lg font-bold text-slate-800">Administrator Access Required</h2>
          <p className="text-sm text-slate-600 mt-1 max-w-md text-center">
            The document catalogue and acquisition portal is restricted to authorized IRIS administrators.
            Your account ({user?.email || 'unauthenticated'}) does not have administrative privileges.
          </p>
        </div>
      </div>
    )
  }

  // Catalogue state
  const [documents, setDocuments] = useState<DiscoveredDocument[]>([])
  const [sources, setSources] = useState<CrawlerSource[]>([])
  const [stats, setStats] = useState<Record<string, number>>({})
  const [latestScan, setLatestScan] = useState<CrawlerScan | null>(null)
  const [activeScanBanner, setActiveScanBanner] = useState<CrawlerScan | null>(null)

  // Filters & Pagination
  const [searchQuery, setSearchQuery] = useState<string>('')
  const [selectedSource, setSelectedSource] = useState<string>('')
  const [selectedStatus, setSelectedStatus] = useState<string>('')
  const [selectedChangeStatus, setSelectedChangeStatus] = useState<string>('')
  const [sortBy, setSortBy] = useState<string>('discovered_at')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')
  const [currentPage, setCurrentPage] = useState<number>(1)
  const [pageSize, setPageSize] = useState<number>(20)
  const [totalPages, setTotalPages] = useState<number>(1)
  const [totalItems, setTotalItems] = useState<number>(0)

  // Loading & Selection
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [isScanning, setIsScanning] = useState<boolean>(false)
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [isBulkProcessing, setIsBulkProcessing] = useState<boolean>(false)
  const [bulkMessage, setBulkMessage] = useState<string | null>(null)
  const [bulkError, setBulkError] = useState<string | null>(null)
  const [feedbackNotice, setFeedbackNotice] = useState<{ type: 'success' | 'error'; message: string } | null>(null)

  // Modal
  const [activeModalDoc, setActiveModalDoc] = useState<DiscoveredDocument | null>(null)

  // Polling refs
  const scanPollRef = useRef<number | null>(null)
  const ingestionPollRef = useRef<number | null>(null)

  const showFeedback = (type: 'success' | 'error', message: string) => {
    setFeedbackNotice({ type, message })
    setTimeout(() => {
      setFeedbackNotice(null)
    }, 5000)
  }

  // 1. Fetch Catalogue Data
  const fetchCatalogue = useCallback(
    async (showLoading: boolean = true) => {
      if (showLoading) setIsLoading(true)
      try {
        const response = await listDiscoveredDocuments({
          page: currentPage,
          pageSize,
          sourceId: selectedSource || undefined,
          status: selectedStatus || undefined,
          changeStatus: selectedChangeStatus || undefined,
          search: searchQuery || undefined,
          sortBy,
          sortOrder,
        })
        setDocuments(response.items)
        setTotalPages(response.total_pages)
        setTotalItems(response.total)
        if (response.stats) {
          setStats(response.stats)
        }
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : 'Failed to load document catalogue'
        showFeedback('error', msg)
      } finally {
        if (showLoading) setIsLoading(false)
      }
    },
    [currentPage, pageSize, selectedSource, selectedStatus, selectedChangeStatus, searchQuery, sortBy, sortOrder],
  )

  // 2. Fetch Auxiliary Stats & Sources (on mount)
  const fetchAuxiliaryData = useCallback(async () => {
    try {
      const [srcList, scanInfo, statsData] = await Promise.all([
        listCrawlerSources(),
        getLatestCrawlerScan(),
        getCrawlerStats(),
      ])
      setSources(srcList)
      setLatestScan(scanInfo)
      setStats(statsData)

      if (scanInfo && scanInfo.status === 'running') {
        setIsScanning(true)
        setActiveScanBanner(scanInfo)
      }
    } catch (err) {
      console.error('Error fetching auxiliary crawler data:', err)
    }
  }, [])

  useEffect(() => {
    fetchCatalogue(true)
  }, [fetchCatalogue])

  useEffect(() => {
    fetchAuxiliaryData()
  }, [fetchAuxiliaryData])

  // 3. Scan Monitoring Polling
  useEffect(() => {
    if (!isScanning) {
      if (scanPollRef.current) {
        clearInterval(scanPollRef.current)
        scanPollRef.current = null
      }
      return
    }

    scanPollRef.current = window.setInterval(async () => {
      try {
        const latest = await getLatestCrawlerScan()
        if (latest) {
          setLatestScan(latest)
          setActiveScanBanner(latest)
          if (latest.status === 'completed' || latest.status === 'failed') {
            setIsScanning(false)
            fetchCatalogue(false)
            fetchAuxiliaryData()

            // Auto-dismiss completed scan banner after 6 seconds so it doesn't push down the catalogue
            setTimeout(() => {
              setActiveScanBanner(null)
            }, 6000)
          }
        }
      } catch (err) {
        console.error('Error polling scan progress:', err)
      }
    }, 2000)

    return () => {
      if (scanPollRef.current) {
        clearInterval(scanPollRef.current)
      }
    }
  }, [isScanning, fetchCatalogue, fetchAuxiliaryData])

  // 4. Live Ingestion Status Polling
  // If any documents in current view are downloading or ingesting, refresh their status
  useEffect(() => {
    const activeDocs = documents.filter(
      (d) => d.status === 'downloading' || d.status === 'ingesting',
    )

    if (activeDocs.length === 0) {
      if (ingestionPollRef.current) {
        clearInterval(ingestionPollRef.current)
        ingestionPollRef.current = null
      }
      return
    }

    ingestionPollRef.current = window.setInterval(async () => {
      try {
        const updates = await Promise.all(
          activeDocs.map(async (doc) => {
            try {
              const statusData = await getDocumentIngestionStatus(doc.id)
              return { id: doc.id, statusData }
            } catch {
              return null
            }
          }),
        )

        let hasTerminalChange = false
        setDocuments((prevDocs) =>
          prevDocs.map((doc) => {
            const update = updates.find((u) => u && u.id === doc.id)
            if (update && update.statusData) {
              const s = update.statusData
              if (s.status !== doc.status) {
                if (s.status === 'ingested' || s.status.includes('failed')) {
                  hasTerminalChange = true
                }
                return {
                  ...doc,
                  status: s.status,
                  change_status: s.change_status,
                  sha256: s.sha256 ?? doc.sha256,
                  local_filename: s.local_filename ?? doc.local_filename,
                  ingested_document_id: s.ingested_document_id ?? doc.ingested_document_id,
                  downloaded_at: s.downloaded_at ?? doc.downloaded_at,
                  ingested_at: s.ingested_at ?? doc.ingested_at,
                  error_message: s.error_message ?? doc.error_message,
                }
              }
            }
            return doc
          }),
        )

        if (hasTerminalChange) {
          fetchAuxiliaryData()
        }
      } catch (err) {
        console.error('Error polling active document status:', err)
      }
    }, 2500)

    return () => {
      if (ingestionPollRef.current) {
        clearInterval(ingestionPollRef.current)
      }
    }
  }, [documents, fetchAuxiliaryData])

  // 5. Trigger Scan Sources
  const handleTriggerScan = async () => {
    if (isScanning) return
    setIsScanning(true)
    try {
      const newScan = await triggerCrawlerScan()
      setLatestScan(newScan)
      setActiveScanBanner(newScan)
      showFeedback('success', 'Discovery scan initiated across all enabled PEC sources.')
    } catch (err: unknown) {
      setIsScanning(false)
      const msg = err instanceof Error ? err.message : 'Failed to initiate crawler scan.'
      showFeedback('error', msg)
    }
  }

  // 6. Approve & Ingest Workflow (Single or Bulk)
  const executeApproveAndIngest = async (targetDocs: DiscoveredDocument[]) => {
    if (targetDocs.length === 0) return
    setIsBulkProcessing(true)
    setBulkError(null)

    let successCount = 0
    let skippedCount = 0
    const failureErrors: string[] = []

    for (let i = 0; i < targetDocs.length; i++) {
      const doc = targetDocs[i]
      setBulkMessage(`Processing ${i + 1} of ${targetDocs.length}: ${doc.title}...`)

      // Workflow check: Do not re-ingest already ingested
      if (doc.status === 'ingested') {
        skippedCount++
        continue
      }

      // Workflow check: Do not silently ingest rejected
      if (doc.status === 'rejected') {
        failureErrors.push(`"${doc.title}" is rejected. Reconsider it first.`)
        continue
      }

      try {
        // Step 1: Approve first if not already approved
        if (doc.status !== 'approved') {
          await approveDocument(doc.id)
        }

        // Step 2: Explicitly initiate acquisition and ingestion
        await ingestDocument(doc.id)
        successCount++
      } catch (err: unknown) {
        const errorMsg = err instanceof Error ? err.message : 'Acquisition failed'
        failureErrors.push(`"${doc.title}": ${errorMsg}`)
      }
    }

    setIsBulkProcessing(false)
    setBulkMessage(null)
    setSelectedIds([])

    // Refresh catalogue to show downloading/ingesting statuses
    await fetchCatalogue(false)
    await fetchAuxiliaryData()

    if (failureErrors.length === 0) {
      const summary =
        successCount === 1
          ? 'Document acquisition and ingestion started.'
          : `${successCount} documents queued for download and ingestion.`
      showFeedback('success', summary)
    } else if (successCount > 0) {
      showFeedback(
        'error',
        `Partial completion: ${successCount} queued, ${failureErrors.length} failed. Errors: ${failureErrors[0]}`,
      )
    } else {
      showFeedback('error', `Operation failed: ${failureErrors[0] || 'Unable to process documents.'}`)
    }
  }

  // 7. Individual Row Action Handlers
  const handleApproveAndIngestSingle = (doc: DiscoveredDocument) => {
    executeApproveAndIngest([doc])
  }

  const handleRejectSingle = async (doc: DiscoveredDocument) => {
    const reason = window.prompt(
      `Reject "${doc.title}"?\nProvide an optional reason for the audit log:`,
      '',
    )
    if (reason === null) return // User cancelled

    try {
      const updated = await rejectDocument(doc.id, reason.trim() || undefined)
      setDocuments((prev) => prev.map((d) => (d.id === doc.id ? updated : d)))
      showFeedback('success', `Marked "${doc.title}" as rejected.`)
      fetchAuxiliaryData()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Rejection failed'
      showFeedback('error', msg)
    }
  }

  const handleReconsiderSingle = async (doc: DiscoveredDocument) => {
    try {
      const updated = await reconsiderDocument(doc.id)
      setDocuments((prev) => prev.map((d) => (d.id === doc.id ? updated : d)))
      showFeedback('success', `Reset "${doc.title}" to discovered for review.`)
      fetchAuxiliaryData()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Reconsideration failed'
      showFeedback('error', msg)
    }
  }

  const handleRetrySingle = async (doc: DiscoveredDocument) => {
    try {
      const updated = await retryDocument(doc.id)
      setDocuments((prev) => prev.map((d) => (d.id === doc.id ? updated : d)))
      showFeedback('success', `Retry initiated for "${doc.title}".`)
      fetchAuxiliaryData()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Retry failed'
      showFeedback('error', msg)
    }
  }

  const handleViewDetails = async (doc: DiscoveredDocument) => {
    setActiveModalDoc(doc)
    try {
      const freshDoc = await getDiscoveredDocument(doc.id)
      setActiveModalDoc(freshDoc)
    } catch {
      // Keep existing doc on error
    }
  }

  // Selection handlers
  const handleToggleSelect = (id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id],
    )
  }

  const handleToggleSelectAll = () => {
    const currentPageIds = documents.map((d) => d.id)
    const allSelected =
      currentPageIds.length > 0 && currentPageIds.every((id) => selectedIds.includes(id))

    if (allSelected) {
      setSelectedIds((prev) => prev.filter((id) => !currentPageIds.includes(id)))
    } else {
      setSelectedIds((prev) => Array.from(new Set([...prev, ...currentPageIds])))
    }
  }

  const handleBulkApproveAndIngest = () => {
    const targetDocs = documents.filter((d) => selectedIds.includes(d.id))
    executeApproveAndIngest(targetDocs)
  }

  return (
    <div className="iris-crawler-admin-container" role="main">
      {/* Feedback Toast */}
      {feedbackNotice && (
        <div
          className={`iris-feedback-toast ${
            feedbackNotice.type === 'success' ? 'iris-toast-success' : 'iris-toast-error'
          }`}
          role="status"
        >
          {feedbackNotice.type === 'success' ? (
            <CheckCircle2 size={16} className="text-emerald-600 flex-shrink-0" />
          ) : (
            <AlertCircle size={16} className="text-rose-600 flex-shrink-0" />
          )}
          <span>{feedbackNotice.message}</span>
        </div>
      )}

      {/* Header Banner */}
      <div className="iris-crawler-header-area">
        <div>
          <h1 className="iris-crawler-page-title">PEC Document Catalogue &amp; Ingestion</h1>
          <p className="iris-crawler-page-subtitle">
            Curated web discovery, change verification, and human-in-the-loop document acquisition for Punjab Engineering College.
          </p>
        </div>
      </div>

      {/* Statistics Overview */}
      <CrawlerStatsOverview
        stats={stats}
        latestScan={latestScan}
        isScanning={isScanning}
        activeStatusFilter={selectedStatus}
        activeChangeFilter={selectedChangeStatus}
        onSelectStatus={(st) => {
          setSelectedStatus(st)
          setCurrentPage(1)
        }}
        onSelectChangeStatus={(cs) => {
          setSelectedChangeStatus(cs)
          setCurrentPage(1)
        }}
      />

      {/* Scan Progress / Results Banner (only displayed during active scan or immediately after) */}
      <ScanProgressBanner
        scan={activeScanBanner}
        isScanning={isScanning}
        onDismiss={() => setActiveScanBanner(null)}
      />

      {/* Filters and Scan Action Bar */}
      <CrawlerFilterBar
        searchQuery={searchQuery}
        onSearchChange={(q) => {
          setSearchQuery(q)
          setCurrentPage(1)
        }}
        selectedSource={selectedSource}
        onSourceChange={(s) => {
          setSelectedSource(s)
          setCurrentPage(1)
        }}
        selectedStatus={selectedStatus}
        onStatusChange={(st) => {
          setSelectedStatus(st)
          setCurrentPage(1)
        }}
        selectedChangeStatus={selectedChangeStatus}
        onChangeStatusChange={(cs) => {
          setSelectedChangeStatus(cs)
          setCurrentPage(1)
        }}
        sortBy={sortBy}
        sortOrder={sortOrder}
        onSortChange={(field, order) => {
          setSortBy(field)
          setSortOrder(order)
          setCurrentPage(1)
        }}
        sources={sources}
        isScanning={isScanning}
        onTriggerScan={handleTriggerScan}
        onRefresh={() => fetchCatalogue(true)}
      />

      {/* Bulk Action Bar (batch approve & ingest at the top) */}
      <BulkActionBar
        selectedCount={selectedIds.length}
        isProcessing={isBulkProcessing}
        processingMessage={bulkMessage}
        error={bulkError}
        onApproveAndIngest={handleBulkApproveAndIngest}
        onClearSelection={() => setSelectedIds([])}
      />

      {/* Discovered Document Table */}
      <DocumentTable
        documents={documents}
        selectedIds={selectedIds}
        onToggleSelect={handleToggleSelect}
        onToggleSelectAll={handleToggleSelectAll}
        onApproveAndIngestSingle={handleApproveAndIngestSingle}
        onRejectSingle={handleRejectSingle}
        onReconsiderSingle={handleReconsiderSingle}
        onRetrySingle={handleRetrySingle}
        onViewDetails={handleViewDetails}
        currentPage={currentPage}
        totalPages={totalPages}
        totalItems={totalItems}
        pageSize={pageSize}
        onPageChange={setCurrentPage}
        onPageSizeChange={(newSize) => {
          setPageSize(newSize)
          setCurrentPage(1)
        }}
        isLoading={isLoading}
      />

      {/* Document Detail & Audit History Modal */}
      <DocumentDetailModal
        document={activeModalDoc}
        onClose={() => setActiveModalDoc(null)}
      />
    </div>
  )
}
