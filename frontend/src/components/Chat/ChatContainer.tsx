import React from 'react'
import { AlertCircle, RefreshCw } from 'lucide-react'
import { WelcomeScreen } from './WelcomeScreen'
import { MessageList } from '../Message/MessageList'
import { MessageComposer } from '../Input/MessageComposer'
import type { ChatMessage, ConnectionStatus } from '../../types/chat'

interface ChatContainerProps {
  messages: ChatMessage[]
  isLoading: boolean
  connectionStatus: ConnectionStatus
  onSendMessage: (query: string) => void
  onRetryMessage: (query: string) => void
  onRecheckConnection?: () => void
}

export const ChatContainer: React.FC<ChatContainerProps> = ({
  messages,
  isLoading,
  connectionStatus,
  onSendMessage,
  onRetryMessage,
  onRecheckConnection,
}) => {
  const isDisconnected = connectionStatus === 'disconnected'

  return (
    <main className="iris-chat-main">
      {isDisconnected && (
        <div className="iris-disconnected-banner" role="alert">
          <div className="iris-disconnected-content">
            <AlertCircle size={16} className="iris-disconnected-icon" />
            <span>
              Backend is currently unreachable. Make sure the FastAPI backend is running on{' '}
              <code>http://127.0.0.1:8000</code>.
            </span>
          </div>
          {onRecheckConnection && (
            <button
              type="button"
              onClick={onRecheckConnection}
              className="iris-btn-reconnect"
              aria-label="Reconnect to backend"
            >
              <RefreshCw size={13} />
              <span>Retry Connection</span>
            </button>
          )}
        </div>
      )}

      <div className="iris-chat-scroll-area">
        {messages.length === 0 ? (
          <WelcomeScreen
            onSelectQuestion={onSendMessage}
            disabled={isLoading || isDisconnected}
          />
        ) : (
          <MessageList
            messages={messages}
            isLoading={isLoading}
            onRetry={onRetryMessage}
          />
        )}
      </div>

      <div className="iris-composer-wrapper">
        <MessageComposer
          onSendMessage={onSendMessage}
          isLoading={isLoading}
          disabled={isDisconnected}
          maxLength={1000}
        />
      </div>
    </main>
  )
}
