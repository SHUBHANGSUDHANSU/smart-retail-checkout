import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError, getSessionById } from '../services/api'
import type { CheckoutSessionDetail } from '../types/history'

export type SessionDetailError = 'not-found' | 'unavailable'

interface SessionDetailState {
  session: CheckoutSessionDetail | null
  isLoading: boolean
  error: SessionDetailError | null
  refresh: () => Promise<void>
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

export function useSessionDetail(sessionId: number): SessionDetailState {
  const [session, setSession] = useState<CheckoutSessionDetail | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<SessionDetailError | null>(null)
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

    const request = getSessionById(sessionId, controller.signal)
      .then((response) => {
        if (!controller.signal.aborted && mountedRef.current) {
          setSession(response)
        }
      })
      .catch((requestError: unknown) => {
        if (controller.signal.aborted || isAbortError(requestError)) {
          return
        }

        console.warn('Checkout session request failed.', requestError)
        if (mountedRef.current) {
          setError(
            requestError instanceof ApiError && requestError.statusCode === 404
              ? 'not-found'
              : 'unavailable',
          )
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
  }, [sessionId])

  useEffect(() => {
    mountedRef.current = true
    void refresh()

    return () => {
      mountedRef.current = false
      controllerRef.current?.abort()
    }
  }, [refresh])

  return { session, isLoading, error, refresh }
}
