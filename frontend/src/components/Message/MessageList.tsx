import React, { useEffect, useRef } from 'react'
import { Sparkles, Loader2 } from 'lucide-react'
import { MessageItem } from './MessageItem'
import type { ChatMessage } from '../../types/chat'

interface MessageListProps {
  messages: ChatMessage[]
  isLoading: boolean
  onRetry?: (query: string) => void
}

export const MessageList: React.FC<MessageListProps> = ({ messages, isLoading, onRetry }) => {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  return (
    <div className="iris-message-list" role="log" aria-live="polite">
      {messages.map((msg) => (
        <MessageItem key={msg.id} message={msg} onRetry={onRetry} />
      ))}

      {isLoading && (
        <div className="iris-message-row iris-message-assistant iris-loading-row">
          <div className="iris-avatar-assistant iris-avatar-pulse" aria-hidden="true">
            <Sparkles size={16} />
          </div>
          <div className="iris-assistant-content-wrapper">
            <div className="iris-card iris-loading-card">
              <div className="iris-loading-content">
                <Loader2 size={16} className="iris-spinner" />
                <span className="iris-loading-text">
                  Searching institutional documents &amp; synthesizing answer...
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      <div ref={bottomRef} className="iris-scroll-anchor" aria-hidden="true" />
    </div>
  )
}
