import { useCallback, useEffect, useRef, useState } from 'react'

import { getMetrics } from '../services/api'
import type { MetricsResponse } from '../types/api'

export const METRICS_POLL_INTERVAL_MS = 2_000

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
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null)
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
    const request = getMetrics(controller.signal)
      .then((snapshot) => {
        if (!controller.signal.aborted && mountedRef.current) {
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
    let pollTimer: ReturnType<typeof setTimeout> | undefined

    const poll = () => {
      void refresh().finally(() => {
        if (mountedRef.current) {
          pollTimer = setTimeout(poll, METRICS_POLL_INTERVAL_MS)
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

  return { metrics, isInitialLoading, error, refresh }
}
