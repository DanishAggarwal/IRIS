import { useCallback, useState } from 'react'
import { sendChatQuery } from '../services/api'
import type { ChatMessage } from '../types/chat'

function generateId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `msg-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isLoading, setIsLoading] = useState<boolean>(false)

  const sendMessage = useCallback(
    async (queryText: string) => {
      const trimmed = queryText.trim()
      if (!trimmed || isLoading) {
        return
      }

      const userMsgId = generateId()
      const userMessage: ChatMessage = {
        id: userMsgId,
        role: 'user',
        content: trimmed,
        timestamp: Date.now(),
      }

      setMessages((prev) => [...prev, userMessage])
      setIsLoading(true)

      try {
        const response = await sendChatQuery({ query: trimmed })

        const assistantMessage: ChatMessage = {
          id: generateId(),
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
      } catch (err: unknown) {
        const errorMessage =
          err instanceof Error
            ? err.message
            : 'An unexpected error occurred while communicating with IRIS.'

        const errorResponse: ChatMessage = {
          id: generateId(),
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
    [isLoading],
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
    sendMessage,
    retryMessage,
    clearChat,
  }
}
