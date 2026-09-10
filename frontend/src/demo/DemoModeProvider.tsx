import {
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'

import { ApiError, getDemoManifest } from '../services/api'
import type { DemoManifest } from '../types/demo'
import { DemoModeContext } from './DemoModeContext'

interface DemoModeProviderProps {
  children: ReactNode
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

export function DemoModeProvider({ children }: DemoModeProviderProps) {
  const [manifest, setManifest] = useState<DemoManifest | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [discoveryError, setDiscoveryError] = useState<string | null>(null)
  const mountedRef = useRef(false)
  const controllerRef = useRef<AbortController | null>(null)
  const requestRef = useRef<Promise<void> | null>(null)

  const refresh = useCallback((): Promise<void> => {
    if (requestRef.current) return requestRef.current
    const controller = new AbortController()
    controllerRef.current = controller

    const request = getDemoManifest(controller.signal)
      .then((nextManifest) => {
        if (!controller.signal.aborted && mountedRef.current) {
          setManifest(nextManifest)
          setDiscoveryError(null)
        }
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted || isAbortError(error)) return
        if (mountedRef.current) {
          if (error instanceof ApiError && error.statusCode === 404) {
            setManifest(null)
            setDiscoveryError(null)
          } else {
            console.warn('Demo mode discovery failed.', error)
            setDiscoveryError('Unable to determine application mode.')
          }
        }
      })
      .finally(() => {
        if (requestRef.current === request) requestRef.current = null
        if (controllerRef.current === controller) controllerRef.current = null
        if (mountedRef.current) setIsLoading(false)
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

  const value = useMemo(
    () => ({ manifest, isLoading, discoveryError, refresh }),
    [manifest, isLoading, discoveryError, refresh],
  )

  return (
    <DemoModeContext.Provider value={value}>
      {children}
    </DemoModeContext.Provider>
  )
}
