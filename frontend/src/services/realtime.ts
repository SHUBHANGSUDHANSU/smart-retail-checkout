import { appConfig } from '../config'
import type { CheckoutActivity } from '../types/history'
import type {
  RealtimeConnectionStatus,
  RealtimeEvent,
} from '../types/realtime'
import { isCartResponse, isCheckoutEvent, isMetricsResponse } from './api'

export const REALTIME_EVENT_TYPES = [
  'cart.updated',
  'checkout.event',
  'metrics.updated',
] as const

interface EventSourceLike {
  addEventListener(type: string, listener: EventListener): void
  removeEventListener(type: string, listener: EventListener): void
  close(): void
  onopen: ((event: Event) => void) | null
  onerror: ((event: Event) => void) | null
}

type EventSourceFactory = (url: string) => EventSourceLike

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isPositiveInteger(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 1
}

function isTimestamp(value: unknown): value is string {
  return typeof value === 'string' && Number.isFinite(Date.parse(value))
}

function isCheckoutActivity(value: unknown): value is CheckoutActivity {
  if (!isRecord(value)) return false
  const normalized = {
    ...value,
    id: value.id ?? 1,
    session_id: value.session_id ?? 1,
  }
  return (
    (value.id === null || isPositiveInteger(value.id)) &&
    (value.session_id === null || isPositiveInteger(value.session_id)) &&
    isCheckoutEvent(normalized)
  )
}

export function parseRealtimeEvent(
  expectedType: string,
  json: string,
): RealtimeEvent | null {
  let value: unknown
  try {
    value = JSON.parse(json)
  } catch {
    return null
  }
  if (
    !isRecord(value) ||
    value.type !== expectedType ||
    !isPositiveInteger(value.sequence) ||
    !isTimestamp(value.timestamp)
  ) {
    return null
  }
  if (value.type === 'cart.updated' && isCartResponse(value.payload)) {
    return value as unknown as RealtimeEvent
  }
  if (value.type === 'checkout.event' && isCheckoutActivity(value.payload)) {
    return value as unknown as RealtimeEvent
  }
  if (value.type === 'metrics.updated' && isMetricsResponse(value.payload)) {
    return value as unknown as RealtimeEvent
  }
  return null
}

export class RealtimeClient {
  private readonly source: EventSourceLike
  private readonly eventListeners = new Set<(event: RealtimeEvent) => void>()
  private readonly statusListeners = new Set<
    (status: RealtimeConnectionStatus) => void
  >()
  private readonly namedListeners = new Map<string, EventListener>()
  private hasConnected = false
  private closed = false

  constructor(
    url: string = appConfig.realtimeStreamUrl,
    factory: EventSourceFactory = (streamUrl) => new EventSource(streamUrl),
  ) {
    this.source = factory(url)
    this.source.onopen = () => {
      this.hasConnected = true
      this.notifyStatus('live')
    }
    this.source.onerror = () => {
      this.notifyStatus(this.hasConnected ? 'reconnecting' : 'offline')
    }
    for (const eventType of REALTIME_EVENT_TYPES) {
      const listener: EventListener = (rawEvent) => {
        if (!(rawEvent instanceof MessageEvent)) return
        const event = parseRealtimeEvent(eventType, String(rawEvent.data))
        if (event === null) {
          console.warn('Ignored malformed realtime message.', eventType)
          return
        }
        this.eventListeners.forEach((callback) => callback(event))
      }
      this.namedListeners.set(eventType, listener)
      this.source.addEventListener(eventType, listener)
    }
  }

  subscribe(listener: (event: RealtimeEvent) => void): () => void {
    this.eventListeners.add(listener)
    return () => this.eventListeners.delete(listener)
  }

  subscribeStatus(
    listener: (status: RealtimeConnectionStatus) => void,
  ): () => void {
    this.statusListeners.add(listener)
    return () => this.statusListeners.delete(listener)
  }

  close(): void {
    if (this.closed) return
    this.closed = true
    this.namedListeners.forEach((listener, eventType) =>
      this.source.removeEventListener(eventType, listener),
    )
    this.source.onopen = null
    this.source.onerror = null
    this.source.close()
    this.eventListeners.clear()
    this.statusListeners.clear()
  }

  private notifyStatus(status: RealtimeConnectionStatus): void {
    if (this.closed) return
    this.statusListeners.forEach((listener) => listener(status))
  }
}
