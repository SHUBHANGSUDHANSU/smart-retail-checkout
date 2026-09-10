import type { MetricsResponse } from './api'
import type { CartResponse } from './cart'
import type { CheckoutActivity } from './history'

export type RealtimeConnectionStatus =
  | 'connecting'
  | 'live'
  | 'reconnecting'
  | 'offline'

interface RealtimeEnvelopeBase {
  sequence: number
  timestamp: string
}

export interface CartUpdatedEvent extends RealtimeEnvelopeBase {
  type: 'cart.updated'
  payload: CartResponse
}

export interface CheckoutEventMessage extends RealtimeEnvelopeBase {
  type: 'checkout.event'
  payload: CheckoutActivity
}

export interface MetricsUpdatedEvent extends RealtimeEnvelopeBase {
  type: 'metrics.updated'
  payload: MetricsResponse
}

export type RealtimeEvent =
  | CartUpdatedEvent
  | CheckoutEventMessage
  | MetricsUpdatedEvent
