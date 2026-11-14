import React from 'react'
import { Header } from './components/Layout/Header'
import { Footer } from './components/Layout/Footer'
import { ChatContainer } from './components/Chat/ChatContainer'
import { useChat } from './hooks/useChat'
import { useHealth } from './hooks/useHealth'

export const App: React.FC = () => {
  const { messages, isLoading, sendMessage, retryMessage, clearChat } = useChat()
  const { status: connectionStatus, recheckHealth } = useHealth()

  return (
    <div className="iris-app-shell">
      <Header
        connectionStatus={connectionStatus}
        hasMessages={messages.length > 0}
        onResetChat={clearChat}
      />

      <ChatContainer
        messages={messages}
        isLoading={isLoading}
        connectionStatus={connectionStatus}
        onSendMessage={sendMessage}
        onRetryMessage={retryMessage}
        onRecheckConnection={recheckHealth}
      />

      <Footer />
    </div>
  )
}

export default App
