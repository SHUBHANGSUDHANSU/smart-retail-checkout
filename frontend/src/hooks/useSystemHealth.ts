import { useCallback, useEffect, useRef, useState } from 'react'

import { getHealth, getReadiness } from '../services/api'
import type { HealthResponse, ReadinessResponse } from '../types/api'

export const HEALTH_POLL_INTERVAL_MS = 5_000

export interface SystemHealthState {
  health: HealthResponse | null
  readiness: ReadinessResponse | null
  isInitialLoading: boolean
  healthError: string | null
  readinessError: string | null
  refresh: () => Promise<void>
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

export function useSystemHealth(): SystemHealthState {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null)
  const [isInitialLoading, setIsInitialLoading] = useState(true)
  const [healthError, setHealthError] = useState<string | null>(null)
  const [readinessError, setReadinessError] = useState<string | null>(null)
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
    const healthRequest = getHealth(controller.signal)
    const readinessRequest = getReadiness(controller.signal)

    const request = Promise.allSettled([healthRequest, readinessRequest])
      .then(([healthResult, readinessResult]) => {
        if (controller.signal.aborted || !mountedRef.current) {
          return
        }

        if (healthResult.status === 'fulfilled') {
          setHealth(healthResult.value)
          setHealthError(null)
        } else if (!isAbortError(healthResult.reason)) {
          console.warn('Backend health request failed.', healthResult.reason)
          setHealthError('Backend unavailable.')
        }

        if (readinessResult.status === 'fulfilled') {
          setReadiness(readinessResult.value)
          setReadinessError(null)
        } else if (!isAbortError(readinessResult.reason)) {
          console.warn('Backend readiness request failed.', readinessResult.reason)
          setReadinessError('Readiness unavailable.')
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
          pollTimer = setTimeout(poll, HEALTH_POLL_INTERVAL_MS)
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

  return {
    health,
    readiness,
    isInitialLoading,
    healthError,
    readinessError,
    refresh,
  }
}
