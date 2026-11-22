import React, { useState } from 'react'
import { Header } from './components/Layout/Header'
import { Footer } from './components/Layout/Footer'
import { ChatContainer } from './components/Chat/ChatContainer'
import { LoginScreen } from './components/Auth/LoginScreen'
import { ConversationSidebar } from './components/Sidebar/ConversationSidebar'
import { useAuth } from './hooks/useAuth'
import { useChat } from './hooks/useChat'
import { useConversations } from './hooks/useConversations'
import { useHealth } from './hooks/useHealth'
import { Loader2 } from 'lucide-react'

export const App: React.FC = () => {
  const { user, isLoading: isAuthLoading, authError, login, logout } = useAuth()
  const { status: connectionStatus, recheckHealth } = useHealth()
  const [isSidebarOpen, setIsSidebarOpen] = useState<boolean>(true)

  const {
    conversations,
    activeConversationId,
    selectConversation,
    startNewChat,
    addOrUpdateSummary,
    renameConversation,
    deleteConversation,
    fetchConversations,
  } = useConversations(Boolean(user))

  const { messages, isLoading, sendMessage, retryMessage } = useChat({
    activeConversationId,
    onConversationCreated: (summary) => {
      addOrUpdateSummary(summary)
      selectConversation(summary.id)
    },
    onConversationUpdated: fetchConversations,
  })

  // Initial authentication check spinner
  if (isAuthLoading) {
    return (
      <div className="iris-app-loading-screen">
        <Loader2 size={32} className="iris-spinner text-blue-600 mb-3" />
        <span className="text-sm font-semibold text-slate-600">
          Connecting to IRIS institutional assistant...
        </span>
      </div>
    )
  }

  // Unauthenticated screen
  if (!user) {
    return (
      <div className="iris-app-shell">
        <LoginScreen onLogin={login} authError={authError} isLoading={isAuthLoading} />
        <Footer />
      </div>
    )
  }

  return (
    <div className="iris-app-shell">
      <Header
        connectionStatus={connectionStatus}
        user={user}
        onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
        onLogout={logout}
      />

      <div className="iris-app-body">
        <ConversationSidebar
          conversations={conversations}
          activeConversationId={activeConversationId}
          isOpen={isSidebarOpen}
          onClose={() => setIsSidebarOpen(false)}
          onSelectConversation={selectConversation}
          onNewChat={startNewChat}
          onRenameConversation={renameConversation}
          onDeleteConversation={deleteConversation}
        />

        <ChatContainer
          messages={messages}
          isLoading={isLoading}
          connectionStatus={connectionStatus}
          onSendMessage={sendMessage}
          onRetryMessage={retryMessage}
          onRecheckConnection={recheckHealth}
        />
      </div>

      <Footer />
    </div>
  )
}

export default App
