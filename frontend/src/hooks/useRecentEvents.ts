import { useCallback, useEffect, useRef, useState } from 'react'

import { getRecentEvents } from '../services/api'
import type { CheckoutActivity } from '../types/history'
import { useRealtime } from '../realtime/RealtimeContext'

export const EVENTS_FALLBACK_INTERVAL_MS = 5_000
export const EVENTS_POLL_INTERVAL_MS = EVENTS_FALLBACK_INTERVAL_MS
export const RECENT_EVENTS_LIMIT = 8

interface RecentEventsState {
  events: CheckoutActivity[] | null
  isInitialLoading: boolean
  error: string | null
  refresh: () => Promise<void>
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

export function useRecentEvents(): RecentEventsState {
  const {
    status: realtimeStatus,
    connectionRevision,
    subscribe: subscribeRealtime,
  } = useRealtime()
  const [events, setEvents] = useState<CheckoutActivity[] | null>(null)
  const [isInitialLoading, setIsInitialLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const mountedRef = useRef(false)
  const controllerRef = useRef<AbortController | null>(null)
  const requestRef = useRef<Promise<void> | null>(null)
  const realtimeRevisionRef = useRef(0)

  const refresh = useCallback((): Promise<void> => {
    const existingRequest = requestRef.current
    if (existingRequest) {
      return existingRequest
    }

    const controller = new AbortController()
    const startingRealtimeRevision = realtimeRevisionRef.current
    controllerRef.current = controller

    const request = getRecentEvents(RECENT_EVENTS_LIMIT, controller.signal)
      .then((response) => {
        if (
          !controller.signal.aborted &&
          mountedRef.current &&
          startingRealtimeRevision === realtimeRevisionRef.current
        ) {
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
    void refresh()

    return () => {
      mountedRef.current = false
      controllerRef.current?.abort()
    }
  }, [refresh])

  useEffect(
    () =>
      subscribeRealtime((event) => {
        if (event.type !== 'checkout.event' || !mountedRef.current) return
        realtimeRevisionRef.current += 1
        const incoming: CheckoutActivity = {
          ...event.payload,
          realtime_sequence: event.sequence,
        }
        setEvents((current) => {
          const existing = current ?? []
          const duplicate = existing.some((candidate) =>
            incoming.id !== null
              ? candidate.id === incoming.id
              : candidate.realtime_sequence === incoming.realtime_sequence,
          )
          return duplicate ? existing : [incoming, ...existing].slice(0, RECENT_EVENTS_LIMIT)
        })
        setError(null)
        setIsInitialLoading(false)
      }),
    [subscribeRealtime],
  )

  useEffect(() => {
    if (realtimeStatus === 'live') return
    let timer: ReturnType<typeof setTimeout>
    let cancelled = false
    const poll = () => {
      void refresh().finally(() => {
        if (mountedRef.current && !cancelled) {
          timer = setTimeout(poll, EVENTS_FALLBACK_INTERVAL_MS)
        }
      })
    }
    timer = setTimeout(poll, EVENTS_FALLBACK_INTERVAL_MS)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [realtimeStatus, refresh])

  useEffect(() => {
    if (connectionRevision > 0) void refresh()
  }, [connectionRevision, refresh])

  return { events, isInitialLoading, error, refresh }
}
