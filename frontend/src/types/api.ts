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
