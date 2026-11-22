import { useCallback, useEffect, useState } from 'react'
import { getConversation, sendChatQuery } from '../services/api'
import type { ConversationSummary, MessageDetail } from '../types/api'
import type { ChatMessage } from '../types/chat'

function generateId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `msg-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

function mapApiMessageToChatMessage(msg: MessageDetail): ChatMessage {
  return {
    id: msg.id,
    conversation_id: msg.conversation_id,
    role: msg.role,
    content: msg.content,
    status: msg.status || undefined,
    citations: msg.citations || [],
    clarification_question: msg.clarification_question,
    handoff_recommendation: msg.handoff_recommendation,
    timestamp: new Date(msg.created_at).getTime(),
  }
}

interface UseChatOptions {
  activeConversationId: string | null
  onConversationCreated?: (summary: ConversationSummary) => void
  onConversationUpdated?: () => void
}

export function useChat({
  activeConversationId,
  onConversationCreated,
  onConversationUpdated,
}: UseChatOptions) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isLoading, setIsLoading] = useState<boolean>(false)
  const [isLoadingHistory, setIsLoadingHistory] = useState<boolean>(false)

  // Load conversation history when activeConversationId changes
  useEffect(() => {
    if (!activeConversationId) {
      setMessages([])
      return
    }

    let isMounted = true
    setIsLoadingHistory(true)

    getConversation(activeConversationId)
      .then((detail) => {
        if (isMounted) {
          const chatMsgs = detail.messages.map(mapApiMessageToChatMessage)
          setMessages(chatMsgs)
        }
      })
      .catch(() => {
        if (isMounted) {
          setMessages([])
        }
      })
      .finally(() => {
        if (isMounted) {
          setIsLoadingHistory(false)
        }
      })

    return () => {
      isMounted = false
    }
  }, [activeConversationId])

  const sendMessage = useCallback(
    async (queryText: string) => {
      const trimmed = queryText.trim()
      if (!trimmed || isLoading) {
        return
      }

      const tempUserMsgId = generateId()
      const userMessage: ChatMessage = {
        id: tempUserMsgId,
        conversation_id: activeConversationId,
        role: 'user',
        content: trimmed,
        timestamp: Date.now(),
      }

      setMessages((prev) => [...prev, userMessage])
      setIsLoading(true)

      try {
        const response = await sendChatQuery({
          query: trimmed,
          conversation_id: activeConversationId,
        })

        const assistantMessage: ChatMessage = {
          id: response.message_id || generateId(),
          conversation_id: response.conversation_id || activeConversationId,
          role: 'assistant',
          status: response.status,
          content: response.answer,
          citations: response.citations,
          clarification_question: response.clarification_question,
          limitations: response.limitations,
          handoff_recommendation: response.handoff_recommendation,
          retrieved_count: response.retrieved_count,
          timestamp: Date.now(),
        }

        setMessages((prev) => [...prev, assistantMessage])

        // If this request started a new conversation, notify parent
        if (response.conversation_id && !activeConversationId) {
          const title = trimmed.length > 50 ? `${trimmed.slice(0, 47)}...` : trimmed
          onConversationCreated?.({
            id: response.conversation_id,
            title,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            message_count: 2,
          })
        } else {
          onConversationUpdated?.()
        }
      } catch (err: unknown) {
        const errorMessage =
          err instanceof Error
            ? err.message
            : 'An unexpected error occurred while communicating with IRIS.'

        const errorResponse: ChatMessage = {
          id: generateId(),
          conversation_id: activeConversationId,
          role: 'assistant',
          status: 'error',
          content: errorMessage,
          error: errorMessage,
          retryQuery: trimmed,
          timestamp: Date.now(),
        }

        setMessages((prev) => [...prev, errorResponse])
      } finally {
        setIsLoading(false)
      }
    },
    [activeConversationId, isLoading, onConversationCreated, onConversationUpdated],
  )

  const retryMessage = useCallback(
    (queryText: string) => {
      sendMessage(queryText)
    },
    [sendMessage],
  )

  const clearChat = useCallback(() => {
    setMessages([])
  }, [])

  return {
    messages,
    isLoading,
    isLoadingHistory,
    sendMessage,
    retryMessage,
    clearChat,
  }
}
