import { describe, expect, it, vi } from 'vitest'

import type { RealtimeEvent } from '../types/realtime'
import { parseRealtimeEvent, RealtimeClient } from './realtime'

const cartMessage = JSON.stringify({
  sequence: 4,
  type: 'cart.updated',
  timestamp: '2026-09-07T12:00:00Z',
  payload: { items: [], total_quantity: 0, total: 0 },
})

class FakeEventSource {
  onopen: ((event: Event) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  readonly listeners = new Map<string, EventListener>()
  close = vi.fn()

  addEventListener(type: string, listener: EventListener): void {
    this.listeners.set(type, listener)
  }

  removeEventListener(type: string): void {
    this.listeners.delete(type)
  }

  emit(type: string, data: string): void {
    this.listeners.get(type)?.(new MessageEvent(type, { data }))
  }
}

describe('realtime transport', () => {
  it('parses a valid typed envelope and rejects malformed data', () => {
    expect(parseRealtimeEvent('cart.updated', cartMessage)).toMatchObject({
      sequence: 4,
      type: 'cart.updated',
    })
    expect(parseRealtimeEvent('metrics.updated', cartMessage)).toBeNull()
    expect(parseRealtimeEvent('cart.updated', '{bad json')).toBeNull()
  })

  it('uses one EventSource for named events and connection state', () => {
    const source = new FakeEventSource()
    const client = new RealtimeClient('/stream', () => source)
    const events: RealtimeEvent[] = []
    const statuses: string[] = []
    client.subscribe((event) => events.push(event))
    client.subscribeStatus((status) => statuses.push(status))

    source.onopen?.(new Event('open'))
    source.emit('cart.updated', cartMessage)
    source.onerror?.(new Event('error'))

    expect(events).toHaveLength(1)
    expect(statuses).toEqual(['live', 'reconnecting'])
    client.close()
    expect(source.close).toHaveBeenCalledOnce()
    expect(source.listeners).toHaveLength(0)
  })

  it('reports offline when the initial connection fails', () => {
    const source = new FakeEventSource()
    const client = new RealtimeClient('/stream', () => source)
    const statuses: string[] = []
    client.subscribeStatus((status) => statuses.push(status))

    source.onerror?.(new Event('error'))

    expect(statuses).toEqual(['offline'])
    client.close()
  })
})
