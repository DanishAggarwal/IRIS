import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App } from '../App'
import type { ChatResponse, HealthResponse } from '../types/api'

describe('App Integration', () => {
  beforeEach(() => {
    vi.restoreAllMocks()

    // Default health mock
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/health')) {
        const mockHealth: HealthResponse = { status: 'ok', service: 'IRIS API' }
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockHealth,
        })
      }
      return Promise.reject(new Error('Unknown url'))
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders application with header, welcome screen, and connected status', async () => {
    render(<App />)

    expect(screen.getByText('IRIS')).toBeInTheDocument()
    expect(screen.getByText("Hello! I'm IRIS.")).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByText('Connected')).toBeInTheDocument()
    })
  })

  it('clicking a suggested question submits chat query and renders answered response', async () => {
    const mockChatResponse: ChatResponse = {
      query: 'What are the course objectives of Cloud Computing?',
      status: 'answered',
      answer: 'The course objectives of Cloud Computing are virtualization and distributed architectures.',
      citations: [
        {
          document: 'CSE_syllabus_24.pdf',
          pages: [117],
          section_title: 'Unit 7',
          is_valid: true,
          claim_supported: true,
        },
      ],
      retrieved_count: 5,
    }

    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/health')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ status: 'ok', service: 'IRIS API' }),
        })
      }
      if (url.includes('/chat')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockChatResponse,
        })
      }
      return Promise.reject(new Error('Unknown url'))
    })

    render(<App />)

    const suggestion = screen.getByText('What are the course objectives of Cloud Computing?')
    fireEvent.click(suggestion)

    // User message bubble should appear
    expect(
      screen.getByText('What are the course objectives of Cloud Computing?'),
    ).toBeInTheDocument()

    // Assistant response should render
    await waitFor(() => {
      expect(
        screen.getByText(
          'The course objectives of Cloud Computing are virtualization and distributed architectures.',
        ),
      ).toBeInTheDocument()
    })

    // Citations should be displayed
    expect(screen.getByText('CSE_syllabus_24.pdf')).toBeInTheDocument()
    expect(screen.getByText('Page 117')).toBeInTheDocument()
  })

  it('submits typed question and renders clarification_needed response', async () => {
    const mockClarificationResponse: ChatResponse = {
      query: 'What is the syllabus of Compiler Design?',
      status: 'clarification_needed',
      answer: 'Multiple courses match.',
      clarification_question: 'Are you referring to UG Compiler Design (CS401) or PG Advanced Compilers (CS701)?',
      citations: [],
      retrieved_count: 5,
    }

    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/health')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ status: 'ok', service: 'IRIS API' }),
        })
      }
      if (url.includes('/chat')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockClarificationResponse,
        })
      }
      return Promise.reject(new Error('Unknown url'))
    })

    const user = userEvent.setup()
    render(<App />)

    const textarea = screen.getByPlaceholderText(/Ask a question about PEC courses/i)
    await user.type(textarea, 'What is the syllabus of Compiler Design?{enter}')

    await waitFor(() => {
      expect(screen.getByText('Clarification Needed')).toBeInTheDocument()
      expect(
        screen.getByText(
          'Are you referring to UG Compiler Design (CS401) or PG Advanced Compilers (CS701)?',
        ),
      ).toBeInTheDocument()
    })
  })

  it('renders handoff_recommended response when evidence is insufficient or waiver requested', async () => {
    const mockHandoffResponse: ChatResponse = {
      query: 'Can my attendance requirement be waived?',
      status: 'handoff_recommended',
      answer: 'Institutional documents do not authorize automatic waivers for attendance below the statutory threshold.',
      handoff_recommendation: 'Dean of Academic Affairs / Senate Disciplinary Committee',
      citations: [
        {
          document: 'CSE_syllabus_24.pdf',
          pages: [12],
          is_valid: true,
          claim_supported: true,
        },
      ],
      retrieved_count: 5,
    }

    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/health')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ status: 'ok', service: 'IRIS API' }),
        })
      }
      if (url.includes('/chat')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockHandoffResponse,
        })
      }
      return Promise.reject(new Error('Unknown url'))
    })

    const user = userEvent.setup()
    render(<App />)

    const textarea = screen.getByPlaceholderText(/Ask a question about PEC courses/i)
    await user.type(textarea, 'Can my attendance requirement be waived?{enter}')

    await waitFor(() => {
      expect(screen.getByText('Administrative Handoff')).toBeInTheDocument()
      expect(
        screen.getByText('Dean of Academic Affairs / Senate Disciplinary Committee'),
      ).toBeInTheDocument()
      expect(
        screen.getByText(
          'Institutional documents do not authorize automatic waivers for attendance below the statutory threshold.',
        ),
      ).toBeInTheDocument()
    })
  })

  it('handles backend network failure and allows retry', async () => {
    let chatCallCount = 0

    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/health')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ status: 'ok', service: 'IRIS API' }),
        })
      }
      if (url.includes('/chat')) {
        chatCallCount++
        if (chatCallCount === 1) {
          // First attempt fails with network error
          return Promise.reject(new TypeError('Failed to fetch'))
        }
        // Second attempt (retry) succeeds
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({
            query: 'Retry query',
            status: 'answered',
            answer: 'Answer after successful retry.',
            citations: [],
            retrieved_count: 3,
          }),
        })
      }
      return Promise.reject(new Error('Unknown url'))
    })

    const user = userEvent.setup()
    render(<App />)

    const textarea = screen.getByPlaceholderText(/Ask a question about PEC courses/i)
    await user.type(textarea, 'Retry query{enter}')

    // Should render error card
    await waitFor(() => {
      expect(screen.getByText('Service Interruption')).toBeInTheDocument()
      expect(
        screen.getByText(
          'IRIS is temporarily unable to connect to its backend. Please try again shortly.',
        ),
      ).toBeInTheDocument()
    })

    // Click retry
    const retryBtn = screen.getByRole('button', { name: /retry sending your question/i })
    fireEvent.click(retryBtn)

    // Should succeed after retry
    await waitFor(() => {
      expect(screen.getByText('Answer after successful retry.')).toBeInTheDocument()
    })
  })

  it('resets conversation when New Chat is clicked in header', async () => {
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/health')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ status: 'ok', service: 'IRIS API' }),
        })
      }
      if (url.includes('/chat')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({
            query: 'Test question',
            status: 'answered',
            answer: 'Test answer.',
            citations: [],
            retrieved_count: 1,
          }),
        })
      }
      return Promise.reject(new Error('Unknown url'))
    })

    const user = userEvent.setup()
    render(<App />)

    const textarea = screen.getByPlaceholderText(/Ask a question about PEC courses/i)
    await user.type(textarea, 'Test question{enter}')

    await waitFor(() => {
      expect(screen.getByText('Test answer.')).toBeInTheDocument()
    })

    // New Chat button should be visible in header
    const resetBtn = screen.getByRole('button', { name: /start a new conversation/i })
    fireEvent.click(resetBtn)

    // Should return to welcome screen
    expect(screen.getByText("Hello! I'm IRIS.")).toBeInTheDocument()
    expect(screen.queryByText('Test answer.')).not.toBeInTheDocument()
  })
})
