import { useCallback, useEffect, useRef, useState } from 'react'

import { getRecentEvents } from '../services/api'
import type { CheckoutEvent } from '../types/history'

export const EVENTS_POLL_INTERVAL_MS = 2_000
export const RECENT_EVENTS_LIMIT = 8

interface RecentEventsState {
  events: CheckoutEvent[] | null
  isInitialLoading: boolean
  error: string | null
  refresh: () => Promise<void>
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

export function useRecentEvents(): RecentEventsState {
  const [events, setEvents] = useState<CheckoutEvent[] | null>(null)
  const [isInitialLoading, setIsInitialLoading] = useState(true)
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

    const request = getRecentEvents(RECENT_EVENTS_LIMIT, controller.signal)
      .then((response) => {
        if (!controller.signal.aborted && mountedRef.current) {
          setEvents(response.events)
          setError(null)
        }
      })
      .catch((requestError: unknown) => {
        if (controller.signal.aborted || isAbortError(requestError)) {
          return
        }

        console.warn('Checkout events request failed.', requestError)
        if (mountedRef.current) {
          setError('Unable to load checkout events.')
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
          setIsInitialLoading(false)
        }
      })

    requestRef.current = request
    return request
  }, [])

  useEffect(() => {
    mountedRef.current = true
    let pollTimer: ReturnType<typeof setTimeout> | undefined

    const poll = () => {
      void refresh().finally(() => {
        if (mountedRef.current) {
          pollTimer = setTimeout(poll, EVENTS_POLL_INTERVAL_MS)
        }
      })
    }

    poll()

    return () => {
      mountedRef.current = false
      if (pollTimer !== undefined) {
        clearTimeout(pollTimer)
      }
      controllerRef.current?.abort()
    }
  }, [refresh])

  return { events, isInitialLoading, error, refresh }
}
