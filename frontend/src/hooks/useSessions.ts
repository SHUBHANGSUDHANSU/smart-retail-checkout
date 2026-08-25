import { useCallback, useEffect, useRef, useState } from 'react'

import { getSessions } from '../services/api'
import type { CheckoutSession } from '../types/history'

export const RECENT_SESSIONS_LIMIT = 20

interface SessionsState {
  sessions: CheckoutSession[] | null
  isLoading: boolean
  error: string | null
  refresh: () => Promise<void>
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

export function useSessions(): SessionsState {
  const [sessions, setSessions] = useState<CheckoutSession[] | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const mountedRef = useRef(false)
  const controllerRef = useRef<AbortController | null>(null)
  const requestRef = useRef<Promise<void> | null>(null)

  const refresh = useCallback((): Promise<void> => {
    const existingRequest = requestRef.current
    if (existingRequest) {
      return existingRequest
    }

    const controller = new AbortController()
    controllerRef.current = controller
    if (mountedRef.current) {
      setIsLoading(true)
      setError(null)
    }

    const request = getSessions(RECENT_SESSIONS_LIMIT, controller.signal)
      .then((response) => {
        if (!controller.signal.aborted && mountedRef.current) {
          setSessions(response.sessions)
        }
      })
      .catch((requestError: unknown) => {
        if (controller.signal.aborted || isAbortError(requestError)) {
          return
        }

        console.warn('Checkout sessions request failed.', requestError)
        if (mountedRef.current) {
          setError('Unable to load checkout sessions.')
        }
      })
      .finally(() => {
        if (controllerRef.current === controller) {
          controllerRef.current = null
        }
        if (requestRef.current === request) {
          requestRef.current = null
        }
        if (mountedRef.current) {
          setIsLoading(false)
        }
      })

    requestRef.current = request
    return request
  }, [])

  useEffect(() => {
    mountedRef.current = true
    void refresh()

    return () => {
      mountedRef.current = false
      controllerRef.current?.abort()
    }
  }, [refresh])

  return { sessions, isLoading, error, refresh }
}
