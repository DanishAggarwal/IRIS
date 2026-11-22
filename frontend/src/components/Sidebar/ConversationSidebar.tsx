import React from 'react'
import { Plus, X, MessageSquareDashed } from 'lucide-react'
import { ConversationItem } from './ConversationItem'
import type { ConversationSummary } from '../../types/api'

interface ConversationSidebarProps {
  conversations: ConversationSummary[]
  activeConversationId: string | null
  isOpen: boolean
  onClose: () => void
  onSelectConversation: (id: string) => void
  onNewChat: () => void
  onRenameConversation: (id: string, newTitle: string) => Promise<void>
  onDeleteConversation: (id: string) => Promise<void>
}

export const ConversationSidebar: React.FC<ConversationSidebarProps> = ({
  conversations,
  activeConversationId,
  isOpen,
  onClose,
  onSelectConversation,
  onNewChat,
  onRenameConversation,
  onDeleteConversation,
}) => {
  return (
    <>
      {/* Mobile backdrop */}
      {isOpen && (
        <div
          className="iris-sidebar-backdrop"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside className={`iris-sidebar ${isOpen ? 'iris-sidebar-open' : ''}`}>
        <div className="iris-sidebar-header">
          <button
            type="button"
            onClick={onNewChat}
            className="iris-btn-new-chat"
            aria-label="Start a new chat conversation"
          >
            <Plus size={16} />
            <span>New Chat</span>
          </button>

          <button
            type="button"
            onClick={onClose}
            className="iris-sidebar-close-btn"
            aria-label="Close sidebar"
          >
            <X size={18} />
          </button>
        </div>

        <div className="iris-sidebar-content">
          <div className="iris-sidebar-section-title">
            <span>Recent Conversations ({conversations.length})</span>
          </div>

          {conversations.length === 0 ? (
            <div className="iris-sidebar-empty">
              <MessageSquareDashed size={24} className="iris-sidebar-empty-icon" />
              <p>No conversation history yet. Start a new chat to begin!</p>
            </div>
          ) : (
            <div className="iris-sidebar-list" role="list">
              {conversations.map((conv) => (
                <ConversationItem
                  key={conv.id}
                  conversation={conv}
                  isActive={conv.id === activeConversationId}
                  onSelect={(id) => {
                    onSelectConversation(id)
                    // Auto-close sidebar on mobile after selection
                    if (window.innerWidth < 768) {
                      onClose()
                    }
                  }}
                  onRename={onRenameConversation}
                  onDelete={onDeleteConversation}
                />
              ))}
            </div>
          )}
        </div>
      </aside>
    </>
  )
}
