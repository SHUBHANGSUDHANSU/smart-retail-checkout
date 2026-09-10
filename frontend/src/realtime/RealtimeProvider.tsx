import {
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'

import { RealtimeClient } from '../services/realtime'
import type {
  RealtimeConnectionStatus,
  RealtimeEvent,
} from '../types/realtime'
import { RealtimeContext } from './RealtimeContext'

export interface RealtimeClientLike {
  subscribe(listener: (event: RealtimeEvent) => void): () => void
  subscribeStatus(
    listener: (status: RealtimeConnectionStatus) => void,
  ): () => void
  close(): void
}

interface RealtimeProviderProps {
  children: ReactNode
  createClient?: () => RealtimeClientLike
}

const defaultCreateClient = () => new RealtimeClient()

export function RealtimeProvider({
  children,
  createClient = defaultCreateClient,
}: RealtimeProviderProps) {
  const [status, setStatus] = useState<RealtimeConnectionStatus>('connecting')
  const [connectionRevision, setConnectionRevision] = useState(0)
  const listenersRef = useRef(new Set<(event: RealtimeEvent) => void>())

  const subscribe = useCallback((listener: (event: RealtimeEvent) => void) => {
    listenersRef.current.add(listener)
    return () => listenersRef.current.delete(listener)
  }, [])

  useEffect(() => {
    const client = createClient()
    const unsubscribeEvents = client.subscribe((event) => {
      listenersRef.current.forEach((listener) => listener(event))
    })
    const unsubscribeStatus = client.subscribeStatus((nextStatus) => {
      setStatus(nextStatus)
      if (nextStatus === 'live') {
        setConnectionRevision((revision) => revision + 1)
      }
    })
    return () => {
      unsubscribeEvents()
      unsubscribeStatus()
      client.close()
    }
  }, [createClient])

  const value = useMemo(
    () => ({ status, connectionRevision, subscribe }),
    [status, connectionRevision, subscribe],
  )

  return (
    <RealtimeContext.Provider value={value}>
      {children}
    </RealtimeContext.Provider>
  )
}
