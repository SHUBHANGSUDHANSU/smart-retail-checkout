import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  RealtimeProvider,
  type RealtimeClientLike,
} from '../realtime/RealtimeProvider'
import { getCart, getMetrics, getRecentEvents, resetCart } from '../services/api'
import type {
  RealtimeConnectionStatus,
  RealtimeEvent,
} from '../types/realtime'
import { useCart } from './useCart'
import { useMetrics } from './useMetrics'
import { useRecentEvents } from './useRecentEvents'

vi.mock('../services/api', () => ({
  getCart: vi.fn(),
  getMetrics: vi.fn(),
  getRecentEvents: vi.fn(),
  resetCart: vi.fn(),
}))

class FakeClient implements RealtimeClientLike {
  eventListener: ((event: RealtimeEvent) => void) | undefined
  statusListener: ((status: RealtimeConnectionStatus) => void) | undefined

  subscribe(listener: (event: RealtimeEvent) => void): () => void {
    this.eventListener = listener
    return () => undefined
  }

  subscribeStatus(
    listener: (status: RealtimeConnectionStatus) => void,
  ): () => void {
    this.statusListener = listener
    return () => undefined
  }

  close(): void {}
}

const emptyMetrics = {
  frames_processed_total: 0,
  dropped_frames_total: 0,
  detections_total: 0,
  active_tracks: 0,
  inference_latency_ms: 0,
  frame_processing_latency_ms: 0,
  current_fps: 0,
  checkout_enter_events_total: 0,
  checkout_exit_events_total: 0,
  cart_additions_total: 0,
  cart_removals_total: 0,
  cart_resets_total: 0,
  current_cart_items: 0,
  current_cart_total: 0,
  uptime_seconds: 0,
  camera_errors_total: 0,
  persistence_errors_total: 0,
}

describe('realtime dashboard hooks', () => {
  beforeEach(() => {
    vi.mocked(getCart).mockResolvedValue({ items: [], total_quantity: 0, total: 0 })
    vi.mocked(getMetrics).mockResolvedValue(emptyMetrics)
    vi.mocked(getRecentEvents).mockResolvedValue({ events: [], limit: 8 })
    vi.mocked(resetCart).mockReset()
  })

  it('loads REST snapshots then applies cart, metrics, and activity messages', async () => {
    const client = new FakeClient()
    const wrapper = ({ children }: { children: ReactNode }) => (
      <RealtimeProvider createClient={() => client}>{children}</RealtimeProvider>
    )
    const view = renderHook(
      () => ({ cart: useCart(), metrics: useMetrics(), events: useRecentEvents() }),
      { wrapper },
    )
    await waitFor(() => expect(view.result.current.cart.cart?.total).toBe(0))

    act(() => client.statusListener?.('live'))
    act(() => {
      client.eventListener?.({
        sequence: 1,
        type: 'cart.updated',
        timestamp: '2026-09-07T12:00:00Z',
        payload: { items: [], total_quantity: 1, total: 40 },
      })
      client.eventListener?.({
        sequence: 2,
        type: 'metrics.updated',
        timestamp: '2026-09-07T12:00:01Z',
        payload: { ...emptyMetrics, frames_processed_total: 12, current_fps: 28 },
      })
      const checkoutEvent: RealtimeEvent = {
        sequence: 3,
        type: 'checkout.event',
        timestamp: '2026-09-07T12:00:01Z',
        payload: {
          id: null,
          session_id: null,
          timestamp: '2026-09-07T12:00:01Z',
          track_id: 7,
          product_id: 'bottle',
          event_type: 'ADD',
          unit_price: 40,
        },
      }
      client.eventListener?.(checkoutEvent)
      client.eventListener?.(checkoutEvent)
    })

    expect(view.result.current.cart.cart?.total).toBe(40)
    expect(view.result.current.metrics.metrics?.current_fps).toBe(28)
    expect(view.result.current.events.events).toHaveLength(1)
    expect(view.result.current.events.events?.[0].realtime_sequence).toBe(3)
    view.unmount()
  })
})
