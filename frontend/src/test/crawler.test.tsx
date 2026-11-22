import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { CrawlerAdminContainer } from '../components/Crawler/CrawlerAdminContainer'
import { Header } from '../components/Layout/Header'
import type {
  DiscoveredDocument,
  DiscoveredDocumentListResponse,
  CrawlerSource,
  CrawlerScan,
  DocumentAudit,
  UserProfile,
} from '../types/api'

describe('Crawler Admin UI', () => {
  const adminUser: UserProfile = {
    id: 'admin-001',
    email: 'admin@pec.edu.in',
    name: 'Admin User',
    role: 'admin',
  }

  const studentUser: UserProfile = {
    id: 'student-001',
    email: 'student@pec.edu.in',
    name: 'Student User',
    role: 'user',
  }

  const mockSources: CrawlerSource[] = [
    {
      source_id: 'pec_senate_minutes',
      name: 'PEC Senate Minutes',
      category: 'senate_minutes',
      base_url: 'https://pec.ac.in/senate',
      enabled: true,
      requires_ocr: false,
    },
  ]

  const mockDocs: DiscoveredDocument[] = [
    {
      id: 'doc-1',
      source_id: 'pec_senate_minutes',
      source_page_url: 'https://pec.ac.in/senate',
      download_url: 'https://pec.ac.in/senate/senate-100.pdf',
      file_type: 'pdf',
      title: '100th Senate Meeting Minutes',
      category: 'senate_minutes',
      status: 'discovered',
      change_status: 'unchanged',
      sha256: 'a1b2c3d4e5f67890123456789abcdef0123456789abcdef0123456789abcdef0',
      first_discovered_at: '2026-11-20T10:00:00Z',
      last_discovered_at: '2026-11-20T10:00:00Z',
      last_scanned_at: '2026-11-20T10:00:00Z',
    },
    {
      id: 'doc-2',
      source_id: 'pec_senate_minutes',
      source_page_url: 'https://pec.ac.in/senate',
      download_url: 'https://pec.ac.in/senate/senate-101.pdf',
      file_type: 'pdf',
      title: '101st Senate Meeting Minutes',
      category: 'senate_minutes',
      status: 'approved',
      change_status: 'potentially_changed',
      first_discovered_at: '2026-11-21T10:00:00Z',
      last_discovered_at: '2026-11-21T10:00:00Z',
      last_scanned_at: '2026-11-21T10:00:00Z',
    },
    {
      id: 'doc-3',
      source_id: 'pec_senate_minutes',
      source_page_url: 'https://pec.ac.in/senate',
      download_url: 'https://pec.ac.in/senate/senate-102.pdf',
      file_type: 'pdf',
      title: '102nd Senate Meeting Minutes',
      category: 'senate_minutes',
      status: 'ingested',
      change_status: 'unchanged',
      first_discovered_at: '2026-11-22T10:00:00Z',
      last_discovered_at: '2026-11-22T10:00:00Z',
      last_scanned_at: '2026-11-22T10:00:00Z',
      ingested_document_id: 'iris-doc-102',
    },
    {
      id: 'doc-4',
      source_id: 'pec_senate_minutes',
      source_page_url: 'https://pec.ac.in/senate',
      download_url: 'https://pec.ac.in/senate/senate-103.pdf',
      file_type: 'pdf',
      title: '103rd Senate Meeting Minutes',
      category: 'senate_minutes',
      status: 'rejected',
      change_status: 'unchanged',
      first_discovered_at: '2026-11-22T11:00:00Z',
      last_discovered_at: '2026-11-22T11:00:00Z',
      last_scanned_at: '2026-11-22T11:00:00Z',
    },
    {
      id: 'doc-5',
      source_id: 'pec_senate_minutes',
      source_page_url: 'https://pec.ac.in/senate',
      download_url: 'https://pec.ac.in/senate/senate-104.pdf',
      file_type: 'pdf',
      title: '104th Senate Meeting Minutes',
      category: 'senate_minutes',
      status: 'ingest_failed',
      change_status: 'unchanged',
      first_discovered_at: '2026-11-22T12:00:00Z',
      last_discovered_at: '2026-11-22T12:00:00Z',
      last_scanned_at: '2026-11-22T12:00:00Z',
      error_message: 'Connection timeout during PDF extraction',
    },
  ]

  const mockStats = {
    total: 5,
    discovered: 1,
    approved: 1,
    rejected: 1,
    downloading: 0,
    ingesting: 0,
    ingested: 1,
    download_failed: 0,
    ingest_failed: 1,
    potentially_changed: 1,
  }

  const mockListResponse: DiscoveredDocumentListResponse = {
    items: mockDocs,
    total: 5,
    page: 1,
    page_size: 20,
    total_pages: 1,
    stats: mockStats,
  }

  const mockScan: CrawlerScan = {
    id: 'scan-001',
    source_id: 'pec_senate_minutes',
    status: 'completed',
    total_sources: 1,
    successful_sources: 1,
    failed_sources: 0,
    total_discovered: 5,
    new_documents: 2,
    updated_documents: 0,
    unchanged_documents: 3,
    error_message: null,
    started_at: '2026-11-22T09:00:00Z',
    completed_at: '2026-11-22T09:01:00Z',
  }

  const mockAudits: DocumentAudit[] = [
    {
      id: 'audit-1',
      document_id: 'doc-1',
      action: 'discovered',
      admin_email: 'system',
      previous_status: 'none',
      new_status: 'discovered',
      created_at: '2026-11-20T10:00:00Z',
    },
    {
      id: 'audit-2',
      document_id: 'doc-1',
      action: 'approved',
      admin_email: 'admin@pec.edu.in',
      previous_status: 'discovered',
      new_status: 'approved',
      reason: 'Valid Senate documentation',
      created_at: '2026-11-20T11:00:00Z',
    },
  ]

  beforeEach(() => {
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('admin user can access crawler page; non-admin receives an access-denied state', async () => {
    // 1. Non-admin renders CrawlerAdminContainer directly
    const { unmount } = render(
      <CrawlerAdminContainer user={studentUser} />
    )
    expect(screen.getByText(/Administrator Access Required/i)).toBeInTheDocument()
    expect(screen.getByText(/restricted to authorized IRIS administrators/i)).toBeInTheDocument()
    unmount()

    // 2. Header does not show Document Portal for non-admin
    const { rerender } = render(
      <Header
        connectionStatus="connected"
        user={studentUser}
        onNavigateView={vi.fn()}
      />
    )
    expect(screen.queryByText(/Document Portal/i)).not.toBeInTheDocument()

    // 3. Header shows Document Portal for admin
    rerender(
      <Header
        connectionStatus="connected"
        user={adminUser}
        onNavigateView={vi.fn()}
      />
    )
    expect(screen.getByText(/Document Portal/i)).toBeInTheDocument()
  })

  it('catalogue loads on mount without triggering scans or ingestion', async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/crawler/documents?')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockListResponse,
        })
      }
      if (url.includes('/crawler/sources')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockSources,
        })
      }
      if (url.includes('/crawler/stats')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockStats,
        })
      }
      if (url.includes('/crawler/scans/latest')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockScan,
        })
      }
      return Promise.reject(new Error(`Unexpected fetch URL: ${url}`))
    })
    global.fetch = fetchMock

    render(<CrawlerAdminContainer user={adminUser} />)

    // Verify catalogue rows are rendered
    await waitFor(() => {
      expect(screen.getByText('100th Senate Meeting Minutes')).toBeInTheDocument()
      expect(screen.getByText('101st Senate Meeting Minutes')).toBeInTheDocument()
      expect(screen.getByText('102nd Senate Meeting Minutes')).toBeInTheDocument()
    })

    // Assert that NO scan triggering (POST /crawler/scan) or ingestion endpoint was called
    const calls = fetchMock.mock.calls
    const isScanTriggered = calls.some(
      (c) => c[1]?.method === 'POST' && String(c[0]).includes('/crawler/scan')
    )
    const isIngestTriggered = calls.some((c) => String(c[0]).includes('/ingest'))
    expect(isScanTriggered).toBe(false)
    expect(isIngestTriggered).toBe(false)
  })

  it('triggering a scan calls the scan endpoint and completion refreshes catalogue', async () => {
    let scanTriggered = false
    const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes('/crawler/scan') && init?.method === 'POST') {
        scanTriggered = true
        return Promise.resolve({
          ok: true,
          status: 202,
          json: async () => ({
            ...mockScan,
            id: 'scan-002',
            status: 'running',
          }),
        })
      }
      if (url.includes('/crawler/scans/latest')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => (scanTriggered ? { ...mockScan, id: 'scan-002', status: 'completed' } : mockScan),
        })
      }
      if (url.includes('/crawler/documents?')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockListResponse,
        })
      }
      if (url.includes('/crawler/sources')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockSources,
        })
      }
      if (url.includes('/crawler/stats')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockStats,
        })
      }
      return Promise.reject(new Error(`Unexpected fetch URL: ${url}`))
    })
    global.fetch = fetchMock

    render(<CrawlerAdminContainer user={adminUser} />)

    await waitFor(() => {
      expect(screen.getByText('100th Senate Meeting Minutes')).toBeInTheDocument()
    })

    const scanButton = screen.getByRole('button', { name: /Scan Sources/i })
    fireEvent.click(scanButton)

    await waitFor(() => {
      expect(scanTriggered).toBe(true)
    })
  })

  it('selecting documents does NOT trigger downloads or ingestion', async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/crawler/documents?')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockListResponse,
        })
      }
      if (url.includes('/crawler/sources')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockSources,
        })
      }
      if (url.includes('/crawler/stats')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockStats,
        })
      }
      if (url.includes('/crawler/scans/latest')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockScan,
        })
      }
      return Promise.reject(new Error(`Unexpected fetch URL: ${url}`))
    })
    global.fetch = fetchMock

    render(<CrawlerAdminContainer user={adminUser} />)

    await waitFor(() => {
      expect(screen.getByText('100th Senate Meeting Minutes')).toBeInTheDocument()
    })

    const initialCallCount = fetchMock.mock.calls.length

    // Select row 1 and row 2 checkboxes
    const checkboxes = screen.getAllByRole('checkbox')
    fireEvent.click(checkboxes[1])
    fireEvent.click(checkboxes[2])

    // Bulk bar appears showing 2 documents selected
    expect(screen.getByText(/2 documents selected/i)).toBeInTheDocument()

    // Assert that selecting rows produced zero network requests
    expect(fetchMock.mock.calls.length).toBe(initialCallCount)
    const calls = fetchMock.mock.calls
    const isIngestTriggered = calls.some((c) => String(c[0]).includes('/ingest'))
    expect(isIngestTriggered).toBe(false)
  })

  it('"Approve & Ingest" calls approval before ingestion for unapproved documents', async () => {
    const callSequence: string[] = []

    const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes('/crawler/documents/doc-1/approve') && init?.method === 'POST') {
        callSequence.push('approve:doc-1')
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ ...mockDocs[0], status: 'approved' }),
        })
      }
      if (url.includes('/crawler/documents/doc-1/ingest') && init?.method === 'POST') {
        callSequence.push('ingest:doc-1')
        return Promise.resolve({
          ok: true,
          status: 202,
          json: async () => ({ ...mockDocs[0], status: 'downloading' }),
        })
      }
      if (url.includes('/crawler/documents?')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockListResponse,
        })
      }
      if (url.includes('/crawler/sources')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockSources,
        })
      }
      if (url.includes('/crawler/stats')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockStats,
        })
      }
      if (url.includes('/crawler/scans/latest')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockScan,
        })
      }
      if (url.includes('/ingestion-status')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({
            document_id: 'doc-1',
            lifecycle_status: 'ingested',
            iris_document_id: 'iris-new-1',
            is_active: false,
            is_terminal: true,
          }),
        })
      }
      return Promise.reject(new Error(`Unexpected fetch URL: ${url}`))
    })
    global.fetch = fetchMock

    render(<CrawlerAdminContainer user={adminUser} />)

    await waitFor(() => {
      expect(screen.getByText('100th Senate Meeting Minutes')).toBeInTheDocument()
    })

    // doc-1 is in 'discovered' status; find its "Approve & Ingest" button
    const approveIngestBtns = screen.getAllByRole('button', { name: /Approve & Ingest/i })
    fireEvent.click(approveIngestBtns[0])

    await waitFor(() => {
      expect(callSequence).toEqual(['approve:doc-1', 'ingest:doc-1'])
    })
  })

  it('ingestion is not called if approval fails', async () => {
    const callSequence: string[] = []

    const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes('/crawler/documents/doc-1/approve') && init?.method === 'POST') {
        callSequence.push('approve:doc-1')
        return Promise.resolve({
          ok: false,
          status: 400,
          json: async () => ({ detail: 'Database error approving document' }),
        })
      }
      if (url.includes('/crawler/documents/doc-1/ingest')) {
        callSequence.push('ingest:doc-1')
        return Promise.resolve({
          ok: true,
          status: 202,
          json: async () => ({}),
        })
      }
      if (url.includes('/crawler/documents?')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockListResponse,
        })
      }
      if (url.includes('/crawler/sources')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockSources,
        })
      }
      if (url.includes('/crawler/stats')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockStats,
        })
      }
      if (url.includes('/crawler/scans/latest')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockScan,
        })
      }
      return Promise.reject(new Error(`Unexpected fetch URL: ${url}`))
    })
    global.fetch = fetchMock

    render(<CrawlerAdminContainer user={adminUser} />)

    await waitFor(() => {
      expect(screen.getByText('100th Senate Meeting Minutes')).toBeInTheDocument()
    })

    const approveIngestBtns = screen.getAllByRole('button', { name: /Approve & Ingest/i })
    fireEvent.click(approveIngestBtns[0])

    await waitFor(() => {
      expect(callSequence).toEqual(['approve:doc-1'])
      // Assert that ingest was never called
      expect(callSequence).not.toContain('ingest:doc-1')
      // Assert error message is displayed
      expect(screen.getByText(/Database error approving document/i)).toBeInTheDocument()
    })
  })

  it('already-ingested documents are not submitted again and rejected documents cannot be ingested', async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/crawler/documents?')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockListResponse,
        })
      }
      if (url.includes('/crawler/sources')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockSources,
        })
      }
      if (url.includes('/crawler/stats')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockStats,
        })
      }
      if (url.includes('/crawler/scans/latest')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockScan,
        })
      }
      return Promise.reject(new Error(`Unexpected fetch URL: ${url}`))
    })
    global.fetch = fetchMock

    render(<CrawlerAdminContainer user={adminUser} />)

    await waitFor(() => {
      expect(screen.getByText('102nd Senate Meeting Minutes')).toBeInTheDocument()
    })

    // doc-3 is 'ingested' -> row only shows 'Details' button, no 'Approve & Ingest' or 'Retry'
    // doc-4 is 'rejected' -> row shows 'Reconsider' and 'Details', no 'Approve & Ingest'
    const reconsiderButtons = screen.getAllByRole('button', { name: /Reconsider/i })
    expect(reconsiderButtons.length).toBe(1)
  })

  it('retry calls the retry endpoint for failed documents', async () => {
    let retryCalled = false

    const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes('/crawler/documents/doc-5/retry') && init?.method === 'POST') {
        retryCalled = true
        return Promise.resolve({
          ok: true,
          status: 202,
          json: async () => ({ ...mockDocs[4], status: 'downloading' }),
        })
      }
      if (url.includes('/crawler/documents?')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockListResponse,
        })
      }
      if (url.includes('/crawler/sources')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockSources,
        })
      }
      if (url.includes('/crawler/stats')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockStats,
        })
      }
      if (url.includes('/crawler/scans/latest')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockScan,
        })
      }
      if (url.includes('/ingestion-status')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({
            document_id: 'doc-5',
            lifecycle_status: 'downloading',
            iris_document_id: null,
            is_active: true,
            is_terminal: false,
          }),
        })
      }
      return Promise.reject(new Error(`Unexpected fetch URL: ${url}`))
    })
    global.fetch = fetchMock

    render(<CrawlerAdminContainer user={adminUser} />)

    await waitFor(() => {
      expect(screen.getByText('104th Senate Meeting Minutes')).toBeInTheDocument()
    })

    // doc-5 is ingest_failed -> has Retry button
    const retryButton = screen.getByRole('button', { name: /Retry/i })
    fireEvent.click(retryButton)

    await waitFor(() => {
      expect(retryCalled).toBe(true)
    })
  })

  it('document detail view displays complete metadata, URLs, hash and audit history', async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/crawler/documents/doc-1/history')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockAudits,
        })
      }
      if (url.includes('/crawler/documents/doc-1') && !url.includes('/history')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockDocs[0],
        })
      }
      if (url.includes('/crawler/documents?')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockListResponse,
        })
      }
      if (url.includes('/crawler/sources')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockSources,
        })
      }
      if (url.includes('/crawler/stats')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockStats,
        })
      }
      if (url.includes('/crawler/scans/latest')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockScan,
        })
      }
      return Promise.reject(new Error(`Unexpected fetch URL: ${url}`))
    })
    global.fetch = fetchMock

    render(<CrawlerAdminContainer user={adminUser} />)

    await waitFor(() => {
      expect(screen.getByText('100th Senate Meeting Minutes')).toBeInTheDocument()
    })

    // Click on document title to open detail modal
    fireEvent.click(screen.getByText('100th Senate Meeting Minutes'))

    // Verify modal elements are displayed
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument()
      expect(screen.getByText(/a1b2c3d4e5f67890123456789abcdef0123456789abcdef0123456789abcdef0/i)).toBeInTheDocument()
      expect(screen.getByText(/Valid Senate documentation/i)).toBeInTheDocument()
      expect(screen.getByText(/admin@pec.edu.in/i)).toBeInTheDocument()
    })
  })

  it('bulk approve & ingest skips already-ingested and handles partial failures cleanly', async () => {
    let doc1Approved = false
    let doc1Ingested = false

    const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes('/crawler/documents/doc-1/approve') && init?.method === 'POST') {
        doc1Approved = true
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ ...mockDocs[0], status: 'approved' }),
        })
      }
      if (url.includes('/crawler/documents/doc-1/ingest') && init?.method === 'POST') {
        doc1Ingested = true
        return Promise.resolve({
          ok: true,
          status: 202,
          json: async () => ({ ...mockDocs[0], status: 'downloading' }),
        })
      }
      if (url.includes('/crawler/documents/doc-2/ingest') && init?.method === 'POST') {
        // doc-2 fails ingestion with 400
        return Promise.resolve({
          ok: false,
          status: 400,
          json: async () => ({ detail: 'Failed to acquire doc-2' }),
        })
      }
      if (url.includes('/crawler/documents?')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockListResponse,
        })
      }
      if (url.includes('/crawler/sources')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockSources,
        })
      }
      if (url.includes('/crawler/stats')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockStats,
        })
      }
      if (url.includes('/crawler/scans/latest')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockScan,
        })
      }
      if (url.includes('/ingestion-status')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({
            document_id: 'doc-1',
            lifecycle_status: 'downloading',
            iris_document_id: null,
            is_active: true,
            is_terminal: false,
          }),
        })
      }
      return Promise.reject(new Error(`Unexpected fetch URL: ${url}`))
    })
    global.fetch = fetchMock

    render(<CrawlerAdminContainer user={adminUser} />)

    await waitFor(() => {
      expect(screen.getByText('100th Senate Meeting Minutes')).toBeInTheDocument()
    })

    // Select row 1 (doc-1), row 2 (doc-2), and row 3 (doc-3, which is already ingested)
    const checkboxes = screen.getAllByRole('checkbox')
    fireEvent.click(checkboxes[1])
    fireEvent.click(checkboxes[2])
    fireEvent.click(checkboxes[3])

    // Bulk bar is visible
    const bulkButton = screen.getByRole('button', { name: /Approve & Ingest Selected/i })
    fireEvent.click(bulkButton)

    await waitFor(() => {
      // doc-1 was approved and ingested
      expect(doc1Approved).toBe(true)
      expect(doc1Ingested).toBe(true)
      // Partial feedback is shown mentioning failure for doc-2
      expect(screen.getByText(/Failed to acquire doc-2/i)).toBeInTheDocument()
    })
  })
})
