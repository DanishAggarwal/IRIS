import { useCallback, useEffect, useState } from 'react'
import {
  deleteConversation,
  listConversations,
  renameConversation,
} from '../services/api'
import type { ConversationSummary } from '../types/api'

export function useConversations(isAuthenticated: boolean) {
  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState<boolean>(false)

  const fetchList = useCallback(async () => {
    if (!isAuthenticated) {
      setConversations([])
      setActiveConversationId(null)
      return
    }

    setIsLoading(true)
    try {
      const res = await listConversations()
      setConversations(res.items)
    } catch {
      // Failed to list conversations
    } finally {
      setIsLoading(false)
    }
  }, [isAuthenticated])

  useEffect(() => {
    fetchList()
  }, [fetchList])

  const selectConversation = useCallback((id: string | null) => {
    setActiveConversationId(id)
  }, [])

  const startNewChat = useCallback(() => {
    setActiveConversationId(null)
  }, [])

  const addOrUpdateSummary = useCallback((summary: ConversationSummary) => {
    setConversations((prev) => {
      const exists = prev.some((c) => c.id === summary.id)
      if (exists) {
        return prev.map((c) => (c.id === summary.id ? summary : c))
      }
      return [summary, ...prev]
    })
  }, [])

  const rename = useCallback(async (id: string, title: string) => {
    const updated = await renameConversation(id, title)
    setConversations((prev) =>
      prev.map((c) => (c.id === id ? { ...c, title: updated.title, updated_at: updated.updated_at } : c))
    )
  }, [])

  const remove = useCallback(async (id: string) => {
    await deleteConversation(id)
    setConversations((prev) => prev.filter((c) => c.id !== id))
    setActiveConversationId((current) => (current === id ? null : current))
  }, [])

  return {
    conversations,
    activeConversationId,
    isLoading,
    fetchConversations: fetchList,
    selectConversation,
    startNewChat,
    addOrUpdateSummary,
    renameConversation: rename,
    deleteConversation: remove,
  }
}
