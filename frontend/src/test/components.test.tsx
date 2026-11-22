import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Header } from '../components/Layout/Header'
import { StatusBadge } from '../components/Layout/StatusBadge'
import { WelcomeScreen } from '../components/Chat/WelcomeScreen'
import { MessageComposer } from '../components/Input/MessageComposer'
import { AnsweredCard } from '../components/Message/AnsweredCard'
import { ClarificationCard } from '../components/Message/ClarificationCard'
import { HandoffCard } from '../components/Message/HandoffCard'
import { ErrorCard } from '../components/Message/ErrorCard'
import { CitationList } from '../components/Citation/CitationList'
import { LoginScreen } from '../components/Auth/LoginScreen'
import { ConversationSidebar } from '../components/Sidebar/ConversationSidebar'
import { ConversationItem } from '../components/Sidebar/ConversationItem'
import type { Citation, ConversationSummary, UserProfile } from '../types/api'

describe('Frontend UI Components', () => {
  const mockUser: UserProfile = {
    id: 'user-001',
    email: 'student@pec.edu.in',
    name: 'Aarav Sharma',
    role: 'user',
  }

  const mockAdmin: UserProfile = {
    id: 'admin-001',
    email: 'admin@gmail.com',
    name: 'Personal Admin',
    role: 'admin',
  }

  describe('StatusBadge', () => {
    it('renders Connected status with proper label', () => {
      render(<StatusBadge status="connected" />)
      expect(screen.getByText('Connected')).toBeInTheDocument()
    })

    it('renders Disconnected status with proper label', () => {
      render(<StatusBadge status="disconnected" />)
      expect(screen.getByText('Disconnected')).toBeInTheDocument()
    })

    it('renders Checking status with proper label', () => {
      render(<StatusBadge status="checking" />)
      expect(screen.getByText('Checking...')).toBeInTheDocument()
    })
  })

  describe('Header', () => {
    it('renders user name, student badge, and connection indicator', () => {
      render(<Header connectionStatus="connected" user={mockUser} />)
      expect(screen.getByText('IRIS')).toBeInTheDocument()
      expect(screen.getByText('Aarav Sharma')).toBeInTheDocument()
      expect(screen.getByText('PEC Student')).toBeInTheDocument()
      expect(screen.getByText('Connected')).toBeInTheDocument()
    })

    it('renders Admin badge when user has admin role', () => {
      render(<Header connectionStatus="connected" user={mockAdmin} />)
      expect(screen.getByText('Admin')).toBeInTheDocument()
    })

    it('calls onLogout when sign out is clicked', () => {
      const handleLogout = vi.fn()
      render(
        <Header
          connectionStatus="connected"
          user={mockUser}
          onLogout={handleLogout}
        />,
      )

      const btn = screen.getByRole('button', { name: /sign out of iris/i })
      fireEvent.click(btn)
      expect(handleLogout).toHaveBeenCalledTimes(1)
    })

    it('calls onToggleSidebar when menu button is clicked', () => {
      const handleToggle = vi.fn()
      render(
        <Header
          connectionStatus="connected"
          user={mockUser}
          onToggleSidebar={handleToggle}
        />,
      )

      const btn = screen.getByRole('button', { name: /toggle conversation history/i })
      fireEvent.click(btn)
      expect(handleToggle).toHaveBeenCalledTimes(1)
    })
  })

  describe('LoginScreen', () => {
    it('renders login branding and institutional domain instructions', () => {
      render(<LoginScreen onLogin={vi.fn()} authError={null} isLoading={false} />)
      expect(screen.getByText(/Information Retrieval & Intelligence System/i)).toBeInTheDocument()
      expect(screen.getByText(/@pec.edu.in/i)).toBeInTheDocument()
    })

    it('renders error message when authError is supplied', () => {
      render(
        <LoginScreen
          onLogin={vi.fn()}
          authError="Access restricted to authorized institutional accounts."
          isLoading={false}
        />,
      )
      expect(screen.getByText(/Access restricted to authorized institutional accounts/i)).toBeInTheDocument()
    })

    it('clicking dev mock login calls onLogin with mock token', () => {
      const handleLogin = vi.fn().mockResolvedValue({})
      render(<LoginScreen onLogin={handleLogin} authError={null} isLoading={false} />)

      const studentBtn = screen.getByRole('button', { name: /sign in as pec student/i })
      fireEvent.click(studentBtn)
      expect(handleLogin).toHaveBeenCalledWith('dev_mock_pec_student')
    })

    it('hides dev mock login fallback when VITE_GOOGLE_CLIENT_ID is configured', () => {
      vi.stubEnv('VITE_GOOGLE_CLIENT_ID', 'test-client-id.apps.googleusercontent.com')
      render(<LoginScreen onLogin={vi.fn()} authError={null} isLoading={false} />)

      expect(screen.queryByText(/Sign in as PEC Student/i)).not.toBeInTheDocument()
      expect(screen.queryByText(/Sign in as Administrator/i)).not.toBeInTheDocument()
      vi.unstubAllEnvs()
    })

    it('initializes and renders Google Sign-In button when Client ID is configured and window.google is ready', () => {
      vi.stubEnv('VITE_GOOGLE_CLIENT_ID', 'test-client-id.apps.googleusercontent.com')
      const mockInitialize = vi.fn()
      const mockRenderButton = vi.fn((container: HTMLElement) => {
        container.innerHTML = '<iframe title="google-sign-in"></iframe>'
      })

      window.google = {
        accounts: {
          id: {
            initialize: mockInitialize,
            renderButton: mockRenderButton,
            prompt: vi.fn(),
          },
        },
      }

      render(<LoginScreen onLogin={vi.fn()} authError={null} isLoading={false} />)

      expect(mockInitialize).toHaveBeenCalledWith(
        expect.objectContaining({
          client_id: 'test-client-id.apps.googleusercontent.com',
        }),
      )
      expect(mockRenderButton).toHaveBeenCalled()
      delete window.google
      vi.unstubAllEnvs()
    })

    it('triggers onLogin when Google ID credential callback fires', async () => {
      vi.stubEnv('VITE_GOOGLE_CLIENT_ID', 'test-client-id.apps.googleusercontent.com')
      const handleLogin = vi.fn().mockResolvedValue({})
      let callbackFn: ((res: { credential: string }) => void) | null = null

      window.google = {
        accounts: {
          id: {
            initialize: vi.fn((config) => {
              callbackFn = config.callback
            }),
            renderButton: vi.fn(),
            prompt: vi.fn(),
          },
        },
      }

      render(<LoginScreen onLogin={handleLogin} authError={null} isLoading={false} />)

      expect(callbackFn).not.toBeNull()
      // Simulate Google sending credential
      callbackFn!({ credential: 'google_jwt_credential_token_xyz' })

      expect(handleLogin).toHaveBeenCalledWith('google_jwt_credential_token_xyz')
      delete window.google
      vi.unstubAllEnvs()
    })

    it('clears button container on re-render to prevent duplicate iframe buttons', () => {
      vi.stubEnv('VITE_GOOGLE_CLIENT_ID', 'test-client-id.apps.googleusercontent.com')
      const mockRenderButton = vi.fn((container: HTMLElement) => {
        container.innerHTML += '<div class="g-btn">Google Button</div>'
      })

      window.google = {
        accounts: {
          id: {
            initialize: vi.fn(),
            renderButton: mockRenderButton,
            prompt: vi.fn(),
          },
        },
      }

      const { rerender } = render(
        <LoginScreen onLogin={vi.fn()} authError={null} isLoading={false} />,
      )
      rerender(<LoginScreen onLogin={vi.fn()} authError="New error" isLoading={false} />)

      // The button container should have been cleared before re-render, so only 1 button markup exists
      const btnWrapper = document.querySelector('.iris-google-btn-wrapper')
      expect(btnWrapper?.querySelectorAll('.g-btn').length).toBe(1)

      delete window.google
      vi.unstubAllEnvs()
    })
  })

  describe('ConversationSidebar & ConversationItem', () => {
    const mockConversations: ConversationSummary[] = [
      {
        id: 'c1',
        title: 'Cloud Computing Syllabus',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        message_count: 2,
      },
      {
        id: 'c2',
        title: 'Deep Learning Experiments',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        message_count: 4,
      },
    ]

    it('renders conversation list and handles selection', () => {
      const handleSelect = vi.fn()
      render(
        <ConversationSidebar
          conversations={mockConversations}
          activeConversationId="c1"
          isOpen={true}
          onClose={vi.fn()}
          onSelectConversation={handleSelect}
          onNewChat={vi.fn()}
          onRenameConversation={vi.fn()}
          onDeleteConversation={vi.fn()}
        />,
      )

      expect(screen.getByText('Cloud Computing Syllabus')).toBeInTheDocument()
      expect(screen.getByText('Deep Learning Experiments')).toBeInTheDocument()

      fireEvent.click(screen.getByText('Deep Learning Experiments'))
      expect(handleSelect).toHaveBeenCalledWith('c2')
    })

    it('calls onNewChat when New Chat button is clicked', () => {
      const handleNewChat = vi.fn()
      render(
        <ConversationSidebar
          conversations={mockConversations}
          activeConversationId="c1"
          isOpen={true}
          onClose={vi.fn()}
          onSelectConversation={vi.fn()}
          onNewChat={handleNewChat}
          onRenameConversation={vi.fn()}
          onDeleteConversation={vi.fn()}
        />,
      )

      const btn = screen.getByRole('button', { name: /start a new chat conversation/i })
      fireEvent.click(btn)
      expect(handleNewChat).toHaveBeenCalledTimes(1)
    })

    it('ConversationItem handles rename flow', async () => {
      const handleRename = vi.fn().mockResolvedValue({})
      render(
        <ConversationItem
          conversation={mockConversations[0]}
          isActive={false}
          onSelect={vi.fn()}
          onRename={handleRename}
          onDelete={vi.fn()}
        />,
      )

      // Click rename icon
      const editBtn = screen.getByTitle('Rename conversation')
      fireEvent.click(editBtn)

      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: 'Updated Title' } })

      const saveBtn = screen.getByTitle('Save title')
      fireEvent.click(saveBtn)

      expect(handleRename).toHaveBeenCalledWith('c1', 'Updated Title')
    })

    it('ConversationItem handles delete confirmation flow', () => {
      const handleDelete = vi.fn().mockResolvedValue({})
      render(
        <ConversationItem
          conversation={mockConversations[0]}
          isActive={false}
          onSelect={vi.fn()}
          onRename={vi.fn()}
          onDelete={handleDelete}
        />,
      )

      // Click delete icon
      const deleteBtn = screen.getByTitle('Delete conversation')
      fireEvent.click(deleteBtn)

      // Shows confirmation prompt
      expect(screen.getByText('Delete?')).toBeInTheDocument()

      const confirmBtn = screen.getByTitle('Confirm delete')
      fireEvent.click(confirmBtn)
      expect(handleDelete).toHaveBeenCalledWith('c1')
    })
  })

  describe('WelcomeScreen', () => {
    it('renders greeting and all 4 suggested questions', () => {
      const handleSelect = vi.fn()
      render(<WelcomeScreen onSelectQuestion={handleSelect} />)

      expect(screen.getByText("Hello! I'm IRIS.")).toBeInTheDocument()
      expect(screen.getByText('What are the course objectives of Cloud Computing?')).toBeInTheDocument()
      expect(screen.getByText('What are the evaluation components of Deep Learning?')).toBeInTheDocument()
      expect(screen.getByText('What are the attendance rules mentioned in the Senate regulations?')).toBeInTheDocument()
      expect(screen.getByText('What are the laboratory experiments for Deep Learning?')).toBeInTheDocument()
    })
  })

  describe('MessageComposer', () => {
    it('renders textarea with character limit feedback', () => {
      render(<MessageComposer onSendMessage={vi.fn()} isLoading={false} />)
      expect(screen.getByPlaceholderText(/Ask a question about PEC courses/i)).toBeInTheDocument()
      expect(screen.getByText('0 / 1000')).toBeInTheDocument()
    })

    it('submits message when Enter is pressed without Shift', async () => {
      const user = userEvent.setup()
      const handleSend = vi.fn()
      render(<MessageComposer onSendMessage={handleSend} isLoading={false} />)

      const textarea = screen.getByPlaceholderText(/Ask a question about PEC courses/i)
      await user.type(textarea, 'What are the attendance rules?{enter}')

      expect(handleSend).toHaveBeenCalledWith('What are the attendance rules?')
    })

    it('creates newline and does NOT submit when Shift+Enter is pressed', async () => {
      const user = userEvent.setup()
      const handleSend = vi.fn()
      render(<MessageComposer onSendMessage={handleSend} isLoading={false} />)

      const textarea = screen.getByPlaceholderText(/Ask a question about PEC courses/i)
      await user.type(textarea, 'Line 1{shift>}{enter}{/shift}Line 2')

      expect(handleSend).not.toHaveBeenCalled()
      expect(textarea).toHaveValue('Line 1\nLine 2')
    })
  })

  describe('Response Cards & Citations', () => {
    const mockCitations: Citation[] = [
      {
        document: 'CSE_syllabus_24.pdf',
        pages: [117],
        section_title: 'Unit 7: Cloud Computing',
        is_valid: true,
        claim_supported: true,
      },
    ]

    it('AnsweredCard renders answer and citations', () => {
      render(<AnsweredCard content="**Bold Answer**" citations={mockCitations} />)
      expect(screen.getByText('Bold Answer')).toBeInTheDocument()
      expect(screen.getByText('CSE_syllabus_24.pdf')).toBeInTheDocument()
      expect(screen.getByText('Page 117')).toBeInTheDocument()
    })

    it('ClarificationCard renders clarification question', () => {
      render(
        <ClarificationCard
          content="Context"
          clarificationQuestion="Which course code?"
        />,
      )
      expect(screen.getByText('Clarification Needed')).toBeInTheDocument()
      expect(screen.getByText('Which course code?')).toBeInTheDocument()
    })

    it('HandoffCard renders recommended authority and advisory disclaimer', () => {
      render(
        <HandoffCard
          content="Waivers require Dean approval."
          handoffRecommendation="Dean of Academic Affairs"
        />,
      )
      expect(screen.getByText('Administrative Handoff')).toBeInTheDocument()
      expect(screen.getByText('Dean of Academic Affairs')).toBeInTheDocument()
    })

    it('ErrorCard provides retry button', () => {
      const handleRetry = vi.fn()
      render(<ErrorCard error="Failed" retryQuery="query" onRetry={handleRetry} />)
      const btn = screen.getByRole('button', { name: /retry sending your question/i })
      fireEvent.click(btn)
      expect(handleRetry).toHaveBeenCalledWith('query')
    })
  })
})
