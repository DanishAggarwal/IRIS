import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { sendChatQuery, checkHealth, getApiBaseUrl, APIError } from '../services/api'
import type { ChatResponse, HealthResponse } from '../types/api'

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
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/health'),
        expect.objectContaining({ method: 'GET' }),
      )
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

      await expect(checkHealth()).rejects.toThrow('Unable to connect to IRIS backend.')
    })
  })

  describe('sendChatQuery', () => {
    it('sends correct JSON payload to POST /chat', async () => {
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
      }

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => mockResponse,
      })

      const result = await sendChatQuery({
        query: 'What are the course objectives of Cloud Computing?',
        top_k: 5,
      })

      expect(result.status).toBe('answered')
      expect(result.citations).toHaveLength(1)
      expect(result.citations[0].document).toBe('CSE_syllabus_24.pdf')
      expect(result.citations[0].pages).toEqual([117])

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/chat'),
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({
            query: 'What are the course objectives of Cloud Computing?',
            top_k: 5,
          }),
        }),
      )
    })

    it('normalizes unexpected internal status to handoff_recommended', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          query: 'Test',
          status: 'insufficient_evidence', // internal status that should not escape
          answer: 'Cannot find facts.',
          citations: [],
          retrieved_count: 3,
        }),
      })

      const result = await sendChatQuery({ query: 'Test' })
      expect(result.status).toBe('handoff_recommended')
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

    it('handles HTTP 503 service unavailable error', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        json: async () => ({ detail: 'Service unavailable' }),
      })

      await expect(sendChatQuery({ query: 'Valid query' })).rejects.toThrow(
        'The IRIS service is temporarily unavailable. Please try again shortly.',
      )
    })

    it('handles HTTP 500 internal server error without exposing technical details', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({ detail: 'Database connection failed at postgres:5432' }),
      })

      await expect(sendChatQuery({ query: 'Valid query' })).rejects.toThrow(
        'An unexpected server error occurred while processing your question.',
      )
    })

    it('handles network failure gracefully', async () => {
      global.fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))

      await expect(sendChatQuery({ query: 'Valid query' })).rejects.toThrow(
        'IRIS is temporarily unable to connect to its backend. Please try again shortly.',
      )
    })

    it('handles malformed JSON body safely', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => {
          throw new SyntaxError('Unexpected token < in JSON at position 0')
        },
      })

      await expect(sendChatQuery({ query: 'Valid query' })).rejects.toThrow(
        'Received an unreadable response from the server.',
      )
    })
  })
})
