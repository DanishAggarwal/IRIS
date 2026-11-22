import type { Citation, PublicResponseStatus } from './api'

export type MessageRole = 'user' | 'assistant'

export type MessageStatus = PublicResponseStatus | 'error'

export interface ChatMessage {
  id: string
  role: MessageRole
  content: string
  status?: MessageStatus
  citations?: Citation[]
  clarification_question?: string | null
  limitations?: string | null
  handoff_recommendation?: string | null
  error?: string | null
  retryQuery?: string
  retrieved_count?: number
  conversation_id?: string | null
  timestamp: number
}

export type ConnectionStatus = 'connected' | 'disconnected' | 'checking'
