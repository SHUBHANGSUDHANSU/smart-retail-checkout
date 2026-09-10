import { act, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'

import type {
  RealtimeConnectionStatus,
  RealtimeEvent,
} from '../types/realtime'
import {
  RealtimeProvider,
  type RealtimeClientLike,
} from './RealtimeProvider'
import { useRealtime } from './RealtimeContext'

class FakeClient implements RealtimeClientLike {
  eventListener: ((event: RealtimeEvent) => void) | undefined
  statusListener: ((status: RealtimeConnectionStatus) => void) | undefined
  close = vi.fn()

  subscribe(listener: (event: RealtimeEvent) => void): () => void {
    this.eventListener = listener
    return () => {
      this.eventListener = undefined
    }
  }

  subscribeStatus(
    listener: (status: RealtimeConnectionStatus) => void,
  ): () => void {
    this.statusListener = listener
    return () => {
      this.statusListener = undefined
    }
  }
}

describe('RealtimeProvider', () => {
  it('shares one connection, dispatches messages, and cleans up', () => {
    const client = new FakeClient()
    const wrapper = ({ children }: { children: ReactNode }) => (
      <RealtimeProvider createClient={() => client}>{children}</RealtimeProvider>
    )
    const view = renderHook(() => useRealtime(), { wrapper })
    const received: RealtimeEvent[] = []
    const unsubscribe = view.result.current.subscribe((event) => received.push(event))

    act(() => client.statusListener?.('live'))
    act(() =>
      client.eventListener?.({
        sequence: 1,
        type: 'cart.updated',
        timestamp: '2026-09-07T12:00:00Z',
        payload: { items: [], total_quantity: 0, total: 0 },
      }),
    )

    expect(view.result.current.status).toBe('live')
    expect(view.result.current.connectionRevision).toBe(1)
    expect(received).toHaveLength(1)
    unsubscribe()
    view.unmount()
    expect(client.close).toHaveBeenCalledOnce()
  })
})
