import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App } from '../App'
import type { ChatResponse, ConversationDetail, ConversationListResponse, HealthResponse, UserProfile } from '../types/api'

describe('App Integration', () => {
  const mockUser: UserProfile = {
    id: 'user-app-001',
    email: 'student@pec.edu.in',
    name: 'Aarav Sharma',
    role: 'user',
  }

  beforeEach(() => {
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders LoginScreen when unauthenticated', async () => {
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/auth/me')) {
        return Promise.resolve({
          ok: false,
          status: 401,
          json: async () => ({ detail: 'Authentication required' }),
        })
      }
      if (url.includes('/health')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ status: 'ok', service: 'IRIS API' }),
        })
      }
      return Promise.reject(new Error('Unknown url'))
    })

    render(<App />)

    await waitFor(() => {
      expect(screen.getByText(/Information Retrieval & Intelligence System/i)).toBeInTheDocument()
      expect(screen.getByText(/Sign in as PEC Student/i)).toBeInTheDocument()
    })
  })

  it('authenticates user and renders chat interface with sidebar', async () => {
    let isAuthenticated = false

    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/auth/me')) {
        if (isAuthenticated) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: async () => mockUser,
          })
        }
        return Promise.resolve({
          ok: false,
          status: 401,
          json: async () => ({ detail: 'Not logged in' }),
        })
      }
      if (url.includes('/auth/google')) {
        isAuthenticated = true
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockUser,
        })
      }
      if (url.includes('/conversations')) {
        const mockList: ConversationListResponse = { items: [], total: 0 }
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockList,
        })
      }
      if (url.includes('/health')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ status: 'ok', service: 'IRIS API' }),
        })
      }
      return Promise.reject(new Error('Unknown url: ' + url))
    })

    render(<App />)

    // Wait for login screen
    await waitFor(() => {
      expect(screen.getByText(/Sign in as PEC Student/i)).toBeInTheDocument()
    })

    // Click Sign In
    const loginBtn = screen.getByRole('button', { name: /sign in as pec student/i })
    fireEvent.click(loginBtn)

    // Should transition to authenticated chat view
    await waitFor(() => {
      expect(screen.getByText("Hello! I'm IRIS.")).toBeInTheDocument()
      expect(screen.getByText('Aarav Sharma')).toBeInTheDocument()
    })
  })

  it('submits a question, creates a conversation, and displays response with citations', async () => {
    const mockChatResponse: ChatResponse = {
      query: 'What are the course objectives of Cloud Computing?',
      status: 'answered',
      answer: 'Cloud Computing objectives cover distributed systems and virtualization.',
      citations: [
        {
          document: 'CSE_syllabus_24.pdf',
          pages: [117],
          section_title: 'Unit 7',
          is_valid: true,
          claim_supported: true,
        },
      ],
      conversation_id: 'conv-new-1',
      message_id: 'msg-new-1',
      retrieved_count: 5,
    }

    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/auth/me')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockUser,
        })
      }
      if (url.includes('/conversations')) {
        const mockList: ConversationListResponse = { items: [], total: 0 }
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockList,
        })
      }
      if (url.includes('/chat')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockChatResponse,
        })
      }
      if (url.includes('/health')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ status: 'ok', service: 'IRIS API' }),
        })
      }
      return Promise.reject(new Error('Unknown url: ' + url))
    })

    render(<App />)

    await waitFor(() => {
      expect(screen.getByText("Hello! I'm IRIS.")).toBeInTheDocument()
    })

    // Click suggested question
    const suggestion = screen.getByText('What are the course objectives of Cloud Computing?')
    fireEvent.click(suggestion)

    // Assistant response and citation must appear
    await waitFor(() => {
      expect(
        screen.getByText('Cloud Computing objectives cover distributed systems and virtualization.'),
      ).toBeInTheDocument()
      expect(screen.getByText('CSE_syllabus_24.pdf')).toBeInTheDocument()
      expect(screen.getByText('Page 117')).toBeInTheDocument()
    })
  })

  it('selecting a past conversation loads historical messages', async () => {
    const pastConvList: ConversationListResponse = {
      items: [
        {
          id: 'conv-history-1',
          title: 'Deep Learning Evaluation',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          message_count: 2,
        },
      ],
      total: 1,
    }

    const pastConvDetail: ConversationDetail = {
      id: 'conv-history-1',
      title: 'Deep Learning Evaluation',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      messages: [
        {
          id: 'm1',
          conversation_id: 'conv-history-1',
          role: 'user',
          content: 'What are evaluation components?',
          created_at: new Date().toISOString(),
        },
        {
          id: 'm2',
          conversation_id: 'conv-history-1',
          role: 'assistant',
          content: 'Midterm 25%, Endsem 50%, Quizzes 25%.',
          status: 'answered',
          citations: [
            {
              document: 'Course Handout Ver 2_0.pdf',
              pages: [7],
              is_valid: true,
              claim_supported: true,
            },
          ],
          created_at: new Date().toISOString(),
        },
      ],
    }

    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/auth/me')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockUser,
        })
      }
      if (url.includes('/conversations/conv-history-1')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => pastConvDetail,
        })
      }
      if (url.includes('/conversations')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => pastConvList,
        })
      }
      if (url.includes('/health')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ status: 'ok', service: 'IRIS API' }),
        })
      }
      return Promise.reject(new Error('Unknown url: ' + url))
    })

    render(<App />)

    // Wait for sidebar item to appear
    await waitFor(() => {
      expect(screen.getByText('Deep Learning Evaluation')).toBeInTheDocument()
    })

    // Click conversation in sidebar
    fireEvent.click(screen.getByText('Deep Learning Evaluation'))

    // Messages should load
    await waitFor(() => {
      expect(screen.getByText('What are evaluation components?')).toBeInTheDocument()
      expect(screen.getByText('Midterm 25%, Endsem 50%, Quizzes 25%.')).toBeInTheDocument()
      expect(screen.getByText('Course Handout Ver 2_0.pdf')).toBeInTheDocument()
    })
  })

  it('clicking New Chat resets active conversation to welcome screen', async () => {
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/auth/me')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockUser,
        })
      }
      if (url.includes('/conversations')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ items: [], total: 0 }),
        })
      }
      if (url.includes('/chat')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({
            query: 'Temporary query',
            status: 'answered',
            answer: 'Temporary answer.',
            citations: [],
            conversation_id: 'conv-temp-1',
          }),
        })
      }
      if (url.includes('/health')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ status: 'ok', service: 'IRIS API' }),
        })
      }
      return Promise.reject(new Error('Unknown url: ' + url))
    })

    const user = userEvent.setup()
    render(<App />)

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/Ask a question about PEC courses/i)).toBeInTheDocument()
    })

    const textarea = screen.getByPlaceholderText(/Ask a question about PEC courses/i)
    fireEvent.change(textarea, { target: { value: 'Temporary query' } })
    const sendBtn = screen.getByRole('button', { name: /^send question$/i })
    fireEvent.click(sendBtn)

    await waitFor(() => {
      expect(screen.getByText('Temporary answer.')).toBeInTheDocument()
    })

    // Click New Chat in sidebar
    const newChatBtn = screen.getByRole('button', { name: /start a new chat conversation/i })
    fireEvent.click(newChatBtn)

    // Should return to welcome screen
    expect(screen.getByText("Hello! I'm IRIS.")).toBeInTheDocument()
    expect(screen.queryByText('Temporary answer.')).not.toBeInTheDocument()
  })

  it('logout signs out user and displays LoginScreen', async () => {
    let loggedOut = false

    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/auth/me')) {
        if (loggedOut) {
          return Promise.resolve({
            ok: false,
            status: 401,
            json: async () => ({ detail: 'Logged out' }),
          })
        }
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockUser,
        })
      }
      if (url.includes('/auth/logout')) {
        loggedOut = true
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ status: 'logged_out' }),
        })
      }
      if (url.includes('/conversations')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ items: [], total: 0 }),
        })
      }
      if (url.includes('/health')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ status: 'ok', service: 'IRIS API' }),
        })
      }
      return Promise.reject(new Error('Unknown url: ' + url))
    })

    render(<App />)

    await waitFor(() => {
      expect(screen.getByText('Aarav Sharma')).toBeInTheDocument()
    })

    const logoutBtn = screen.getByRole('button', { name: /sign out of iris/i })
    fireEvent.click(logoutBtn)

    // Should return to LoginScreen
    await waitFor(() => {
      expect(screen.getByText(/Information Retrieval & Intelligence System/i)).toBeInTheDocument()
      expect(screen.getByText(/Sign in as PEC Student/i)).toBeInTheDocument()
    })
  })
})
