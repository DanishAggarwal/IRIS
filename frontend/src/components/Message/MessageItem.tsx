import React from 'react'
import { User, Sparkles } from 'lucide-react'
import { AnsweredCard } from './AnsweredCard'
import { ClarificationCard } from './ClarificationCard'
import { HandoffCard } from './HandoffCard'
import { ErrorCard } from './ErrorCard'
import type { ChatMessage } from '../../types/chat'

interface MessageItemProps {
  message: ChatMessage
  onRetry?: (query: string) => void
}

function formatTime(timestamp: number): string {
  const date = new Date(timestamp)
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export const MessageItem: React.FC<MessageItemProps> = ({ message, onRetry }) => {
  const isUser = message.role === 'user'

  if (isUser) {
    return (
      <div className="iris-message-row iris-message-user">
        <div className="iris-message-bubble-user">
          <div className="iris-user-text">{message.content}</div>
          <div className="iris-message-time-user">{formatTime(message.timestamp)}</div>
        </div>
        <div className="iris-avatar-user" aria-hidden="true" title="Student">
          <User size={16} />
        </div>
      </div>
    )
  }

  // Assistant message
  return (
    <div className="iris-message-row iris-message-assistant">
      <div className="iris-avatar-assistant" aria-hidden="true" title="IRIS Assistant">
        <Sparkles size={16} />
      </div>

      <div className="iris-assistant-content-wrapper">
        <div className="iris-assistant-header">
          <span className="iris-assistant-name">IRIS</span>
          <span className="iris-message-time-assistant">{formatTime(message.timestamp)}</span>
        </div>

        {message.status === 'answered' && (
          <AnsweredCard
            content={message.content}
            citations={message.citations}
            limitations={message.limitations}
          />
        )}

        {message.status === 'clarification_needed' && (
          <ClarificationCard
            content={message.content}
            clarificationQuestion={message.clarification_question}
          />
        )}

        {message.status === 'handoff_recommended' && (
          <HandoffCard
            content={message.content}
            handoffRecommendation={message.handoff_recommendation}
            citations={message.citations}
          />
        )}

        {message.status === 'error' && (
          <ErrorCard
            error={message.error || message.content}
            retryQuery={message.retryQuery}
            onRetry={onRetry}
          />
        )}

        {!message.status && (
          <AnsweredCard
            content={message.content}
            citations={message.citations}
            limitations={message.limitations}
          />
        )}
      </div>
    </div>
  )
}
