export type CartEventType = 'ADD' | 'REMOVE' | 'RESET'

export interface CheckoutEvent {
  id: number
  session_id: number
  timestamp: string
  track_id: number | null
  product_id: string | null
  event_type: CartEventType
  unit_price: number | null
}

export interface RecentEventsResponse {
  events: CheckoutEvent[]
  limit: number
}

export interface CheckoutSession {
  id: number
  started_at: string
  ended_at: string | null
  final_total: number | null
}

export interface RecentSessionsResponse {
  sessions: CheckoutSession[]
  limit: number
}

export interface CheckoutSessionDetail extends CheckoutSession {
  events: CheckoutEvent[]
}
