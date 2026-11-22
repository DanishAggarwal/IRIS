/**
 * API types mirroring the FastAPI backend schemas in api/schemas.py.
 */

export interface PageSpan {
  start_char?: number
  end_char?: number
  page?: number
  [key: string]: unknown
}

export interface Citation {
  document: string
  pages: number[]
  section_title?: string | null
  page_spans?: PageSpan[]
  claim?: string | null
  is_valid: boolean
  claim_supported: boolean
}

export type PublicResponseStatus = 'answered' | 'clarification_needed' | 'handoff_recommended'

export interface ChatRequest {
  query: string
  top_k?: number
  conversation_id?: string | null
}

export interface ChatResponse {
  query: string
  status: PublicResponseStatus
  answer: string
  citations: Citation[]
  clarification_question?: string | null
  limitations?: string | null
  handoff_recommendation?: string | null
  retrieved_count: number
  conversation_id?: string | null
  message_id?: string | null
}

export interface UserProfile {
  id: string
  email: string
  name: string
  profile_picture_url?: string | null
  role: 'user' | 'admin'
}

export interface MessageDetail {
  id: string
  conversation_id: string
  role: 'user' | 'assistant'
  content: string
  status?: PublicResponseStatus | null
  citations?: Citation[] | null
  clarification_question?: string | null
  handoff_recommendation?: string | null
  created_at: string
}

export interface ConversationSummary {
  id: string
  title: string
  created_at: string
  updated_at: string
  message_count: number
}

export interface ConversationDetail {
  id: string
  title: string
  created_at: string
  updated_at: string
  messages: MessageDetail[]
}

export interface ConversationListResponse {
  items: ConversationSummary[]
  total: number
}

export interface HealthResponse {
  status: string
  service: string
}

export interface ReadinessResponse {
  status: string
  service: string
  database: string
  configuration: string
  detail?: string | null
}

export interface APIErrorDetail {
  detail: string
}

export interface CrawlerSource {
  id: string
  source_id: string
  name: string
  url: string
  category: string
  strategy: string
  enabled: boolean
  config?: Record<string, unknown> | null
  last_scanned_at?: string | null
  created_at: string
  updated_at: string
}

export type DocumentLifecycleStatus =
  | 'discovered'
  | 'pending_approval'
  | 'approved'
  | 'rejected'
  | 'downloading'
  | 'ingesting'
  | 'ingested'
  | 'download_failed'
  | 'ingest_failed'

export type DocumentChangeStatus = 'unknown' | 'unchanged' | 'potentially_changed'

export interface DiscoveredDocument {
  id: string
  source_id: string
  title: string
  source_page_url: string
  download_url: string
  category: string
  file_type: string
  publication_date?: string | null
  meeting_number?: string | null
  academic_year?: string | null
  status: DocumentLifecycleStatus | string
  change_status: DocumentChangeStatus | string
  http_etag?: string | null
  http_last_modified?: string | null
  http_content_length?: number | null
  last_checked_at?: string | null
  rejection_reason?: string | null
  approved_by?: string | null
  approved_at?: string | null
  local_filename?: string | null
  ingested_document_id?: string | null
  downloaded_at?: string | null
  ingested_at?: string | null
  error_message?: string | null
  sha256?: string | null
  first_discovered_at: string
  last_discovered_at: string
  last_scanned_at: string
  metadata?: Record<string, unknown> | null
}

export interface DiscoveredDocumentListResponse {
  items: DiscoveredDocument[]
  total: number
  page: number
  page_size: number
  total_pages: number
  stats: Record<string, number>
}

export interface DocumentAudit {
  id: string
  document_id: string
  admin_email: string
  action: string
  previous_status: string
  new_status: string
  reason?: string | null
  created_at: string
}

export interface CrawlerScan {
  id: string
  source_id?: string | null
  status: 'running' | 'completed' | 'failed' | string
  total_sources: number
  total_discovered: number
  new_documents: number
  updated_documents: number
  potentially_changed: number
  error_message?: string | null
  initiated_by: string
  started_at: string
  completed_at?: string | null
}

export interface DocumentIngestionStatus {
  id: string
  title: string
  download_url: string
  status: string
  change_status: string
  sha256?: string | null
  local_filename?: string | null
  ingested_document_id?: string | null
  downloaded_at?: string | null
  ingested_at?: string | null
  error_message?: string | null
}
