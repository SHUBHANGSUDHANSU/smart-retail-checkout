import { createContext, useContext } from 'react'

import type {
  RealtimeConnectionStatus,
  RealtimeEvent,
} from '../types/realtime'

export interface RealtimeContextValue {
  status: RealtimeConnectionStatus
  connectionRevision: number
  subscribe: (listener: (event: RealtimeEvent) => void) => () => void
}

export const RealtimeContext = createContext<RealtimeContextValue>({
  status: 'offline',
  connectionRevision: 0,
  subscribe: () => () => undefined,
})

export function useRealtime(): RealtimeContextValue {
  return useContext(RealtimeContext)
}
