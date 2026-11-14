import type { ChatRequest, ChatResponse, HealthResponse, PublicResponseStatus } from '../types/api'

export class APIError extends Error {
  statusCode?: number
  isNetworkError: boolean

  constructor(message: string, statusCode?: number, isNetworkError: boolean = false) {
    super(message)
    this.name = 'APIError'
    this.statusCode = statusCode
    this.isNetworkError = isNetworkError
  }
}

/**
 * Get the backend API base URL from Vite environment variables.
 * Falls back to local development URL http://127.0.0.1:8000.
 */
export function getApiBaseUrl(): string {
  const envUrl = import.meta.env.VITE_API_BASE_URL
  if (typeof envUrl === 'string' && envUrl.trim().length > 0) {
    return envUrl.replace(/\/+$/, '')
  }
  return 'http://127.0.0.1:8000'
}

/**
 * Check backend liveness via GET /health.
 */
export async function checkHealth(): Promise<HealthResponse> {
  const baseUrl = getApiBaseUrl()
  try {
    const response = await fetch(`${baseUrl}/health`, {
      method: 'GET',
      headers: {
        Accept: 'application/json',
      },
    })

    if (!response.ok) {
      throw new APIError('Backend health check returned non-200 status', response.status)
    }

    const data = (await response.json()) as HealthResponse
    return data
  } catch (error) {
    if (error instanceof APIError) {
      throw error
    }
    throw new APIError('Unable to connect to IRIS backend.', undefined, true)
  }
}

/**
 * Send student question to POST /chat.
 */
export async function sendChatQuery(request: ChatRequest): Promise<ChatResponse> {
  const baseUrl = getApiBaseUrl()

  let response: Response
  try {
    response = await fetch(`${baseUrl}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(request),
    })
  } catch {
    throw new APIError(
      'IRIS is temporarily unable to connect to its backend. Please try again shortly.',
      undefined,
      true,
    )
  }

  // Handle HTTP error statuses gracefully
  if (!response.ok) {
    let detail = ''
    try {
      const errJson = await response.json()
      if (typeof errJson.detail === 'string') {
        detail = errJson.detail
      } else if (Array.isArray(errJson.detail) && errJson.detail.length > 0) {
        detail = errJson.detail.map((d: { msg?: string }) => d.msg || '').filter(Boolean).join('; ')
      }
    } catch {
      // Body wasn't JSON
    }

    if (response.status === 422) {
      throw new APIError(
        detail || 'Your question could not be processed. Please check the length and format.',
        422,
      )
    }

    if (response.status === 503) {
      throw new APIError(
        'The IRIS service is temporarily unavailable. Please try again shortly.',
        503,
      )
    }

    if (response.status >= 500) {
      throw new APIError(
        'An unexpected server error occurred while processing your question.',
        response.status,
      )
    }

    throw new APIError(
      detail || `Request failed with status ${response.status}`,
      response.status,
    )
  }

  // Parse JSON response safely
  let data: unknown
  try {
    data = await response.json()
  } catch {
    throw new APIError('Received an unreadable response from the server.')
  }

  // Validate response structure
  if (!data || typeof data !== 'object') {
    throw new APIError('Received an invalid response format from the server.')
  }

  const res = data as Partial<ChatResponse>
  if (typeof res.answer !== 'string' || typeof res.status !== 'string') {
    throw new APIError('Response missing required fields from the server.')
  }

  // Normalise status to public statuses only
  let normStatus: PublicResponseStatus = 'handoff_recommended'
  if (res.status === 'answered' || res.status === 'clarification_needed') {
    normStatus = res.status
  }

  return {
    query: typeof res.query === 'string' ? res.query : request.query,
    status: normStatus,
    answer: res.answer,
    citations: Array.isArray(res.citations) ? res.citations : [],
    clarification_question: res.clarification_question || null,
    limitations: res.limitations || null,
    handoff_recommendation: res.handoff_recommendation || null,
    retrieved_count: typeof res.retrieved_count === 'number' ? res.retrieved_count : 0,
  }
}
