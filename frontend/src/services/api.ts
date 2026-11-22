import type {
  ChatRequest,
  ChatResponse,
  ConversationDetail,
  ConversationListResponse,
  HealthResponse,
  PublicResponseStatus,
  UserProfile,
} from '../types/api'

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
 * Automatically aligns with window.location.hostname (localhost vs 127.0.0.1)
 * to guarantee schemeful same-site cookie delivery in all browsers.
 */
export function getApiBaseUrl(): string {
  const envUrl = import.meta.env.VITE_API_BASE_URL
  let baseUrl = 'http://localhost:8000'

  if (typeof envUrl === 'string' && envUrl.trim().length > 0) {
    baseUrl = envUrl.replace(/\/+$/, '')
  }

  // If in browser on local loopback, match API hostname to the browser's current address
  if (typeof window !== 'undefined' && window.location) {
    const currentHost = window.location.hostname
    if (currentHost === '127.0.0.1' && baseUrl.includes('localhost')) {
      baseUrl = baseUrl.replace('//localhost', '//127.0.0.1')
    } else if (currentHost === 'localhost' && baseUrl.includes('127.0.0.1')) {
      baseUrl = baseUrl.replace('//127.0.0.1', '//localhost')
    }
  }

  return baseUrl
}

/**
 * Helper to execute a fetch request with credentials and error parsing.
 */
async function fetchWithAuth(
  endpoint: string,
  options: RequestInit = {},
): Promise<Response> {
  const baseUrl = getApiBaseUrl()
  const url = `${baseUrl}${endpoint.startsWith('/') ? '' : '/'}${endpoint}`

  try {
    const res = await fetch(url, {
      ...options,
      credentials: 'include',
      headers: {
        Accept: 'application/json',
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...options.headers,
      },
    })
    return res
  } catch {
    throw new APIError(
      'IRIS is temporarily unable to connect to its backend. Please try again shortly.',
      undefined,
      true,
    )
  }
}

/**
 * Parse JSON safely from Response or throw standard error.
 */
async function parseResponseJson<T>(response: Response): Promise<T> {
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

    if (response.status === 401) {
      throw new APIError(detail || 'Session expired or authentication required.', 401)
    }

    if (response.status === 403) {
      throw new APIError(detail || 'Access restricted to authorized institutional accounts.', 403)
    }

    if (response.status === 404) {
      throw new APIError(detail || 'Requested resource not found.', 404)
    }

    if (response.status === 422) {
      throw new APIError(detail || 'Your request contains invalid parameters.', 422)
    }

    if (response.status === 503) {
      throw new APIError(
        detail || 'The IRIS service is temporarily unavailable. Please try again shortly.',
        503,
      )
    }

    if (response.status >= 500) {
      throw new APIError('An unexpected server error occurred.', response.status)
    }

    throw new APIError(detail || `Request failed with status ${response.status}`, response.status)
  }

  try {
    return (await response.json()) as T
  } catch {
    throw new APIError('Received an unreadable response from the server.')
  }
}

/**
 * Check backend liveness via GET /health.
 */
export async function checkHealth(): Promise<HealthResponse> {
  const response = await fetchWithAuth('/health', { method: 'GET' })
  return parseResponseJson<HealthResponse>(response)
}

/**
 * Authenticate with Google ID token via POST /auth/google.
 */
export async function loginWithGoogle(idToken: string): Promise<UserProfile> {
  const response = await fetchWithAuth('/auth/google', {
    method: 'POST',
    body: JSON.stringify({ id_token: idToken }),
  })
  return parseResponseJson<UserProfile>(response)
}

/**
 * Get current authenticated user profile via GET /auth/me.
 */
export async function getCurrentUser(): Promise<UserProfile> {
  const response = await fetchWithAuth('/auth/me', { method: 'GET' })
  return parseResponseJson<UserProfile>(response)
}

/**
 * Logout and revoke session via POST /auth/logout.
 */
export async function logout(): Promise<void> {
  await fetchWithAuth('/auth/logout', { method: 'POST' })
}

/**
 * List the current user's conversations via GET /conversations.
 */
export async function listConversations(
  limit: number = 50,
  offset: number = 0,
): Promise<ConversationListResponse> {
  const response = await fetchWithAuth(`/conversations?limit=${limit}&offset=${offset}`, {
    method: 'GET',
  })
  return parseResponseJson<ConversationListResponse>(response)
}

/**
 * Create a new conversation via POST /conversations.
 */
export async function createConversation(title?: string): Promise<ConversationDetail> {
  const response = await fetchWithAuth('/conversations', {
    method: 'POST',
    body: JSON.stringify({ title: title || null }),
  })
  return parseResponseJson<ConversationDetail>(response)
}

/**
 * Retrieve a conversation and its messages via GET /conversations/{id}.
 */
export async function getConversation(conversationId: string): Promise<ConversationDetail> {
  const response = await fetchWithAuth(`/conversations/${conversationId}`, {
    method: 'GET',
  })
  return parseResponseJson<ConversationDetail>(response)
}

/**
 * Rename a conversation via PATCH /conversations/{id}.
 */
export async function renameConversation(
  conversationId: string,
  newTitle: string,
): Promise<ConversationDetail> {
  const response = await fetchWithAuth(`/conversations/${conversationId}`, {
    method: 'PATCH',
    body: JSON.stringify({ title: newTitle }),
  })
  return parseResponseJson<ConversationDetail>(response)
}

/**
 * Delete a conversation via DELETE /conversations/{id}.
 */
export async function deleteConversation(conversationId: string): Promise<void> {
  const response = await fetchWithAuth(`/conversations/${conversationId}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    await parseResponseJson(response)
  }
}

/**
 * Send student question to POST /chat with conversation persistence.
 */
export async function sendChatQuery(request: ChatRequest): Promise<ChatResponse> {
  const response = await fetchWithAuth('/chat', {
    method: 'POST',
    body: JSON.stringify(request),
  })

  const rawData = await parseResponseJson<Record<string, unknown>>(response)

  if (typeof rawData.answer !== 'string' || typeof rawData.status !== 'string') {
    throw new APIError('Response missing required fields from the server.')
  }

  let normStatus: PublicResponseStatus = 'handoff_recommended'
  if (rawData.status === 'answered' || rawData.status === 'clarification_needed') {
    normStatus = rawData.status
  }

  return {
    query: typeof rawData.query === 'string' ? rawData.query : request.query,
    status: normStatus,
    answer: rawData.answer,
    citations: Array.isArray(rawData.citations) ? rawData.citations : [],
    clarification_question: (rawData.clarification_question as string) || null,
    limitations: (rawData.limitations as string) || null,
    handoff_recommendation: (rawData.handoff_recommendation as string) || null,
    retrieved_count: typeof rawData.retrieved_count === 'number' ? rawData.retrieved_count : 0,
    conversation_id: (rawData.conversation_id as string) || null,
    message_id: (rawData.message_id as string) || null,
  }
}
