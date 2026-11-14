import { useCallback, useEffect, useState } from 'react'
import { checkHealth } from '../services/api'
import type { ConnectionStatus } from '../types/chat'

export function useHealth(pollIntervalMs: number = 45000) {
  const [status, setStatus] = useState<ConnectionStatus>('checking')

  const verifyHealth = useCallback(async () => {
    try {
      await checkHealth()
      setStatus('connected')
    } catch {
      setStatus('disconnected')
    }
  }, [])

  useEffect(() => {
    verifyHealth()

    const interval = setInterval(() => {
      verifyHealth()
    }, pollIntervalMs)

    return () => clearInterval(interval)
  }, [verifyHealth, pollIntervalMs])

  return {
    status,
    recheckHealth: verifyHealth,
  }
}
