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
