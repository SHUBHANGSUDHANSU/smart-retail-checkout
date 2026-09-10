import { useCallback, useEffect, useRef, useState } from 'react'

import { getMetrics } from '../services/api'
import type { MetricsResponse } from '../types/api'
import { useRealtime } from '../realtime/RealtimeContext'

export const METRICS_FALLBACK_INTERVAL_MS = 5_000
export const METRICS_POLL_INTERVAL_MS = METRICS_FALLBACK_INTERVAL_MS

interface MetricsState {
  metrics: MetricsResponse | null
  isInitialLoading: boolean
  error: string | null
  refresh: () => Promise<void>
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

export function useMetrics(): MetricsState {
  const {
    status: realtimeStatus,
    connectionRevision,
    subscribe: subscribeRealtime,
  } = useRealtime()
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null)
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
    const request = getMetrics(controller.signal)
      .then((snapshot) => {
        if (
          !controller.signal.aborted &&
          mountedRef.current &&
          startingRealtimeRevision === realtimeRevisionRef.current
        ) {
          setMetrics(snapshot)
          setError(null)
        }
      })
      .catch((requestError: unknown) => {
        if (controller.signal.aborted || isAbortError(requestError)) {
          return
        }

        console.warn('Metrics request failed.', requestError)
        if (mountedRef.current) {
          setError('Unable to refresh metrics.')
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
        if (event.type === 'metrics.updated' && mountedRef.current) {
          realtimeRevisionRef.current += 1
          setMetrics(event.payload)
          setError(null)
          setIsInitialLoading(false)
        }
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
          timer = setTimeout(poll, METRICS_FALLBACK_INTERVAL_MS)
        }
      })
    }
    timer = setTimeout(poll, METRICS_FALLBACK_INTERVAL_MS)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [realtimeStatus, refresh])

  useEffect(() => {
    if (connectionRevision > 0) void refresh()
  }, [connectionRevision, refresh])

  return { metrics, isInitialLoading, error, refresh }
}
