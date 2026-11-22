import React, { useState } from 'react'
import { Sparkles, Maximize2, Minus, MessageSquare, Bot } from 'lucide-react'
import { MessageList } from '../Message/MessageList'
import { MessageComposer } from '../Input/MessageComposer'
import type { ChatMessage, ConnectionStatus } from '../../types/chat'

interface MiniChatAssistantProps {
  messages: ChatMessage[]
  isLoading: boolean
  connectionStatus: ConnectionStatus
  onSendMessage: (query: string) => void
  onRetryMessage: (query: string) => void
  onExpandToFullScreen: () => void
}

const QUICK_PROMPTS = [
  'When will the midterm exams take place?',
  'What are the attendance rules at PEC?',
  'What are the course objectives of Cloud Computing?',
]

export const MiniChatAssistant: React.FC<MiniChatAssistantProps> = ({
  messages,
  isLoading,
  connectionStatus,
  onSendMessage,
  onRetryMessage,
  onExpandToFullScreen,
}) => {
  const [isOpen, setIsOpen] = useState<boolean>(false)
  const isDisconnected = connectionStatus === 'disconnected'

  return (
    <>
      {/* Floating Launcher Trigger */}
      {!isOpen && (
        <button
          type="button"
          onClick={() => setIsOpen(true)}
          className="iris-floating-assistant-launcher"
          aria-label="Open IRIS Assistant"
          title="Open Grounded IRIS Assistant"
        >
          <div className="iris-floating-launcher-pulse" />
          <Sparkles size={18} className="iris-sparkle-spin" />
          <span className="font-semibold text-sm">Ask IRIS Assistant</span>
          {messages.length > 0 && (
            <span className="iris-floating-badge">{messages.length}</span>
          )}
        </button>
      )}

      {/* Floating Quarter-Size Mini Assistant Panel */}
      {isOpen && (
        <aside
          className="iris-mini-assistant-panel"
          role="complementary"
          aria-label="IRIS AI Assistant Mini Panel"
        >
          {/* Header */}
          <div className="iris-mini-assistant-header">
            <div className="iris-mini-assistant-title-group">
              <div className="iris-mini-avatar">
                <Bot size={16} />
              </div>
              <div>
                <div className="flex items-center gap-1.5">
                  <h3 className="iris-mini-title">IRIS Assistant</h3>
                  <span className="iris-mini-status-dot" title="Connected" />
                </div>
                <p className="iris-mini-subtitle">Grounded institutional intelligence</p>
              </div>
            </div>

            <div className="iris-mini-header-actions">
              <button
                type="button"
                onClick={onExpandToFullScreen}
                className="iris-btn-mini-action"
                title="Expand to Full Screen Chat"
                aria-label="Expand to full screen chat"
              >
                <Maximize2 size={14} />
              </button>
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="iris-btn-mini-action"
                title="Minimize Assistant"
                aria-label="Minimize assistant"
              >
                <Minus size={15} />
              </button>
            </div>
          </div>

          {/* Conversation Scroll Body */}
          <div className="iris-mini-assistant-body">
            {messages.length === 0 ? (
              <div className="iris-mini-welcome">
                <div className="iris-mini-welcome-icon">
                  <Sparkles size={28} className="text-blue-600" />
                </div>
                <h4 className="text-sm font-semibold text-slate-800 mb-1">
                  How can I help you today?
                </h4>
                <p className="text-xs text-slate-500 mb-4 text-center max-w-xs">
                  Ask questions about academic calendars, syllabus, senate meetings, or institutional policies.
                </p>

                <div className="iris-mini-suggestions">
                  <p className="text-[11px] font-medium text-slate-400 mb-2 uppercase tracking-wider">
                    Suggested Questions
                  </p>
                  {QUICK_PROMPTS.map((q, idx) => (
                    <button
                      key={idx}
                      type="button"
                      className="iris-mini-suggestion-pill"
                      onClick={() => onSendMessage(q)}
                      disabled={isLoading || isDisconnected}
                    >
                      <MessageSquare size={12} className="flex-shrink-0 text-blue-500" />
                      <span>{q}</span>
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="iris-mini-messages-wrapper">
                <MessageList
                  messages={messages}
                  isLoading={isLoading}
                  onRetry={onRetryMessage}
                />
              </div>
            )}
          </div>

          {/* Message Composer Footer */}
          <div className="iris-mini-assistant-footer">
            <MessageComposer
              onSendMessage={onSendMessage}
              isLoading={isLoading}
              disabled={isDisconnected}
              maxLength={1000}
            />
          </div>
        </aside>
      )}
    </>
  )
}
