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
import type { Citation } from '../types/api'

describe('Frontend UI Components', () => {
  describe('StatusBadge', () => {
    it('renders Connected status with proper label', () => {
      render(<StatusBadge status="connected" />)
      expect(screen.getByText('Connected')).toBeInTheDocument()
      expect(screen.getByRole('status')).toHaveAttribute(
        'aria-label',
        'Backend connection: Connected',
      )
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
    it('renders title, badge, and connection indicator', () => {
      render(<Header connectionStatus="connected" hasMessages={false} />)
      expect(screen.getByText('IRIS')).toBeInTheDocument()
      expect(
        screen.getByText('Information Retrieval & Intelligence System'),
      ).toBeInTheDocument()
      expect(screen.getByText('Connected')).toBeInTheDocument()
    })

    it('shows New Chat button when messages exist and calls onResetChat', () => {
      const handleReset = vi.fn()
      render(
        <Header
          connectionStatus="connected"
          hasMessages={true}
          onResetChat={handleReset}
        />,
      )

      const btn = screen.getByRole('button', { name: /start a new conversation/i })
      expect(btn).toBeInTheDocument()
      fireEvent.click(btn)
      expect(handleReset).toHaveBeenCalledTimes(1)
    })
  })

  describe('WelcomeScreen', () => {
    it('renders greeting and all 4 suggested questions', () => {
      const handleSelect = vi.fn()
      render(<WelcomeScreen onSelectQuestion={handleSelect} />)

      expect(screen.getByText("Hello! I'm IRIS.")).toBeInTheDocument()
      expect(
        screen.getByText('What are the course objectives of Cloud Computing?'),
      ).toBeInTheDocument()
      expect(
        screen.getByText('What are the evaluation components of Deep Learning?'),
      ).toBeInTheDocument()
      expect(
        screen.getByText('What are the attendance rules mentioned in the Senate regulations?'),
      ).toBeInTheDocument()
      expect(
        screen.getByText('What are the laboratory experiments for Deep Learning?'),
      ).toBeInTheDocument()
    })

    it('clicking a suggested question calls onSelectQuestion with question text', () => {
      const handleSelect = vi.fn()
      render(<WelcomeScreen onSelectQuestion={handleSelect} />)

      const suggestion = screen.getByText('What are the course objectives of Cloud Computing?')
      fireEvent.click(suggestion)

      expect(handleSelect).toHaveBeenCalledWith(
        'What are the course objectives of Cloud Computing?',
      )
    })
  })

  describe('MessageComposer', () => {
    it('renders textarea with character limit feedback', () => {
      render(<MessageComposer onSendMessage={vi.fn()} isLoading={false} />)
      expect(
        screen.getByPlaceholderText(/Ask a question about PEC courses/i),
      ).toBeInTheDocument()
      expect(screen.getByText('0 / 1000')).toBeInTheDocument()
    })

    it('disables send button when input is empty or whitespace', () => {
      render(<MessageComposer onSendMessage={vi.fn()} isLoading={false} />)
      const sendBtn = screen.getByRole('button', { name: /send question/i })
      expect(sendBtn).toBeDisabled()
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

    it('enforces character limit and warns user when exceeded', async () => {
      const user = userEvent.setup()
      const handleSend = vi.fn()
      render(<MessageComposer onSendMessage={handleSend} isLoading={false} maxLength={20} />)

      const textarea = screen.getByPlaceholderText(/Ask a question about PEC courses/i)
      await user.type(textarea, 'This string is way longer than twenty characters!')

      expect(screen.getByText(/Exceeds 20 character limit/i)).toBeInTheDocument()
      const sendBtn = screen.getByRole('button', { name: /send question/i })
      expect(sendBtn).toBeDisabled()
    })

    it('disables input when isLoading is true', () => {
      render(<MessageComposer onSendMessage={vi.fn()} isLoading={true} />)
      const textarea = screen.getByPlaceholderText(/Ask a question about PEC courses/i)
      expect(textarea).toBeDisabled()
    })
  })

  describe('CitationList and CitationItem', () => {
    const mockCitations: Citation[] = [
      {
        document: 'CSE_syllabus_24.pdf',
        pages: [117],
        section_title: 'Unit 7: Cloud Computing',
        claim: 'Course objectives cover virtualization and distributed systems',
        is_valid: true,
        claim_supported: true,
      },
      {
        document: 'Course Handout Ver 2_0.pdf',
        pages: [7, 8],
        section_title: 'Evaluation Criteria',
        is_valid: true,
        claim_supported: true,
      },
    ]

    it('displays document names, page numbers, and page ranges accurately', () => {
      render(<CitationList citations={mockCitations} />)

      expect(screen.getByText('Institutional Sources (2)')).toBeInTheDocument()
      expect(screen.getByText('CSE_syllabus_24.pdf')).toBeInTheDocument()
      expect(screen.getByText('Page 117')).toBeInTheDocument()
      expect(screen.getByText('Course Handout Ver 2_0.pdf')).toBeInTheDocument()
      expect(screen.getByText('Pages 7–8')).toBeInTheDocument()
    })

    it('shows section titles and toggles extra details on click', () => {
      render(<CitationList citations={mockCitations} />)

      expect(screen.getByText('Unit 7: Cloud Computing')).toBeInTheDocument()

      const toggleBtn = screen.getByRole('button', { name: /toggle citation 1 details/i })
      fireEvent.click(toggleBtn)

      expect(
        screen.getByText(/Course objectives cover virtualization and distributed systems/i),
      ).toBeInTheDocument()
      expect(screen.getByText(/Verified against institutional text/i)).toBeInTheDocument()
    })
  })

  describe('Response Cards', () => {
    it('AnsweredCard renders markdown text and citations', () => {
      const citations: Citation[] = [
        {
          document: 'CSE_syllabus_24.pdf',
          pages: [45],
          is_valid: true,
          claim_supported: true,
        },
      ]
      render(
        <AnsweredCard
          content="**Bold Answer** with [link or bullet] details."
          citations={citations}
          limitations="Informational limitation"
        />,
      )

      expect(screen.getByText('Bold Answer')).toBeInTheDocument()
      expect(screen.getByText('Informational limitation')).toBeInTheDocument()
      expect(screen.getByText('CSE_syllabus_24.pdf')).toBeInTheDocument()
    })

    it('ClarificationCard renders clarification question and continuation hint', () => {
      render(
        <ClarificationCard
          content="Multiple courses match."
          clarificationQuestion="Which specific course code are you referring to?"
        />,
      )

      expect(screen.getByText('Clarification Needed')).toBeInTheDocument()
      expect(
        screen.getByText('Which specific course code are you referring to?'),
      ).toBeInTheDocument()
      expect(
        screen.getByText(/Please enter your clarification in the message box below/i),
      ).toBeInTheDocument()
    })

    it('HandoffCard renders administrative guidance and recommended authority', () => {
      render(
        <HandoffCard
          content="This rule requires an institutional waiver not found in the documents."
          handoffRecommendation="Academic Section / Dean of Academic Affairs"
        />,
      )

      expect(screen.getByText('Administrative Handoff')).toBeInTheDocument()
      expect(
        screen.getByText(/This rule requires an institutional waiver/i),
      ).toBeInTheDocument()
      expect(
        screen.getByText('Academic Section / Dean of Academic Affairs'),
      ).toBeInTheDocument()
      expect(
        screen.getByText(/Please verify requirements and deadlines directly/i),
      ).toBeInTheDocument()
    })

    it('ErrorCard renders error message and provides retry button', () => {
      const handleRetry = vi.fn()
      render(
        <ErrorCard
          error="Network connection timed out."
          retryQuery="Original query"
          onRetry={handleRetry}
        />,
      )

      expect(screen.getByText('Service Interruption')).toBeInTheDocument()
      expect(screen.getByText('Network connection timed out.')).toBeInTheDocument()

      const retryBtn = screen.getByRole('button', { name: /retry sending your question/i })
      fireEvent.click(retryBtn)
      expect(handleRetry).toHaveBeenCalledWith('Original query')
    })
  })
})
