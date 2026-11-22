import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  sendChatQuery,
  checkHealth,
  getApiBaseUrl,
  loginWithGoogle,
  getCurrentUser,
  logout,
  listConversations,
  createConversation,
  getConversation,
  renameConversation,
  deleteConversation,
  APIError,
} from '../services/api'
import type { ChatResponse, HealthResponse, UserProfile, ConversationListResponse, ConversationDetail } from '../types/api'

describe('services/api', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('getApiBaseUrl', () => {
    it('returns a default or configured URL without trailing slashes', () => {
      const url = getApiBaseUrl()
      expect(url).toBeTruthy()
      expect(url.endsWith('/')).toBe(false)
    })

    it('aligns localhost URL to 127.0.0.1 when running on 127.0.0.1 hostname', () => {
      const originalLocation = window.location
      Object.defineProperty(window, 'location', {
        value: { hostname: '127.0.0.1' },
        writable: true,
      })
      vi.stubEnv('VITE_API_BASE_URL', 'http://localhost:8000')

      expect(getApiBaseUrl()).toBe('http://127.0.0.1:8000')

      Object.defineProperty(window, 'location', {
        value: originalLocation,
        writable: true,
      })
      vi.unstubAllEnvs()
    })
  })

  describe('checkHealth', () => {
    it('returns HealthResponse when endpoint returns 200', async () => {
      const mockHealth: HealthResponse = { status: 'ok', service: 'IRIS API' }
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => mockHealth,
      })

      const res = await checkHealth()
      expect(res.status).toBe('ok')
      expect(res.service).toBe('IRIS API')
    })

    it('throws APIError when endpoint returns non-200', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
      })

      await expect(checkHealth()).rejects.toThrow(APIError)
    })

    it('throws network APIError when fetch fails', async () => {
      global.fetch = vi.fn().mockRejectedValue(new Error('Network offline'))

      await expect(checkHealth()).rejects.toThrow('IRIS is temporarily unable to connect to its backend. Please try again shortly.')
    })
  })

  describe('Authentication services', () => {
    it('loginWithGoogle sends id_token and returns UserProfile', async () => {
      const mockUser: UserProfile = {
        id: 'user-123',
        email: 'student@pec.edu.in',
        name: 'PEC Student',
        role: 'user',
      }

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => mockUser,
      })

      const res = await loginWithGoogle('valid-google-jwt')
      expect(res.email).toBe('student@pec.edu.in')
      expect(res.role).toBe('user')

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/auth/google'),
        expect.objectContaining({
          method: 'POST',
          credentials: 'include',
          body: JSON.stringify({ id_token: 'valid-google-jwt' }),
        }),
      )
    })

    it('loginWithGoogle handles 403 access restricted', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 403,
        json: async () => ({ detail: 'Access restricted to authorized institutional accounts.' }),
      })

      await expect(loginWithGoogle('outsider-token')).rejects.toThrow(
        'Access restricted to authorized institutional accounts.',
      )
    })

    it('getCurrentUser returns UserProfile when authenticated', async () => {
      const mockUser: UserProfile = {
        id: 'admin-1',
        email: 'admin@gmail.com',
        name: 'Administrator',
        role: 'admin',
      }

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => mockUser,
      })

      const res = await getCurrentUser()
      expect(res.role).toBe('admin')
      expect(res.name).toBe('Administrator')
    })

    it('logout posts to /auth/logout', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ status: 'logged_out' }),
      })

      await logout()
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/auth/logout'),
        expect.objectContaining({ method: 'POST', credentials: 'include' }),
      )
    })
  })

  describe('Conversation services', () => {
    it('listConversations fetches paginated history', async () => {
      const mockList: ConversationListResponse = {
        items: [
          {
            id: 'conv-1',
            title: 'Cloud Computing',
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            message_count: 2,
          },
        ],
        total: 1,
      }

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => mockList,
      })

      const res = await listConversations(50, 0)
      expect(res.total).toBe(1)
      expect(res.items[0].title).toBe('Cloud Computing')
    })

    it('createConversation sends title', async () => {
      const mockDetail: ConversationDetail = {
        id: 'conv-new',
        title: 'New Chat Thread',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        messages: [],
      }

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 201,
        json: async () => mockDetail,
      })

      const res = await createConversation('New Chat Thread')
      expect(res.id).toBe('conv-new')
      expect(res.title).toBe('New Chat Thread')
    })

    it('getConversation returns conversation and messages', async () => {
      const mockDetail: ConversationDetail = {
        id: 'conv-123',
        title: 'Deep Learning',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        messages: [
          {
            id: 'msg-1',
            conversation_id: 'conv-123',
            role: 'user',
            content: 'What are evaluation components?',
            created_at: new Date().toISOString(),
          },
        ],
      }

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => mockDetail,
      })

      const res = await getConversation('conv-123')
      expect(res.messages).toHaveLength(1)
      expect(res.messages[0].content).toBe('What are evaluation components?')
    })

    it('renameConversation patches title', async () => {
      const mockUpdated: ConversationDetail = {
        id: 'conv-123',
        title: 'Renamed Title',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        messages: [],
      }

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => mockUpdated,
      })

      const res = await renameConversation('conv-123', 'Renamed Title')
      expect(res.title).toBe('Renamed Title')
    })

    it('deleteConversation issues DELETE request', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ status: 'deleted' }),
      })

      await deleteConversation('conv-123')
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/conversations/conv-123'),
        expect.objectContaining({ method: 'DELETE' }),
      )
    })
  })

  describe('sendChatQuery', () => {
    it('sends correct JSON payload to POST /chat with conversation_id', async () => {
      const mockResponse: ChatResponse = {
        query: 'What are the course objectives of Cloud Computing?',
        status: 'answered',
        answer: 'The course objectives of Cloud Computing include understanding virtualization...',
        citations: [
          {
            document: 'CSE_syllabus_24.pdf',
            pages: [117],
            section_title: 'Unit 7',
            is_valid: true,
            claim_supported: true,
          },
        ],
        clarification_question: null,
        limitations: null,
        handoff_recommendation: null,
        retrieved_count: 5,
        conversation_id: 'conv-777',
        message_id: 'msg-888',
      }

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => mockResponse,
      })

      const result = await sendChatQuery({
        query: 'What are the course objectives of Cloud Computing?',
        conversation_id: 'conv-777',
        top_k: 5,
      })

      expect(result.status).toBe('answered')
      expect(result.conversation_id).toBe('conv-777')
      expect(result.message_id).toBe('msg-888')

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/chat'),
        expect.objectContaining({
          method: 'POST',
          credentials: 'include',
          body: JSON.stringify({
            query: 'What are the course objectives of Cloud Computing?',
            conversation_id: 'conv-777',
            top_k: 5,
          }),
        }),
      )
    })

    it('handles HTTP 422 validation error', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: async () => ({ detail: 'Query cannot be empty or contain only whitespace.' }),
      })

      await expect(sendChatQuery({ query: '   ' })).rejects.toThrow(
        'Query cannot be empty or contain only whitespace.',
      )
    })

    it('handles HTTP 500 internal server error without exposing technical details', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({ detail: 'Database connection failed at postgres:5432' }),
      })

      await expect(sendChatQuery({ query: 'Valid query' })).rejects.toThrow(
        'An unexpected server error occurred.',
      )
    })

    it('handles HTTP 503 capacity limit error displaying the friendly message', async () => {
      const quotaMsg =
        'IRIS is currently experiencing high demand and has temporarily reached its AI provider capacity limit. Please wait a moment and click \'Retry question\'.'
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        json: async () => ({ detail: quotaMsg }),
      })

      await expect(sendChatQuery({ query: 'Valid query' })).rejects.toThrow(quotaMsg)
    })
  })
})
