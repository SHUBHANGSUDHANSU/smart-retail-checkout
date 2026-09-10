import { appConfig } from '../config'
import type {
  ApplicationState,
  HealthResponse,
  MetricsResponse,
  ReadinessComponentStatus,
  ReadinessResponse,
} from '../types/api'
import type { CartItem, CartResetResponse, CartResponse } from '../types/cart'
import type {
  CartEventType,
  CheckoutEvent,
  CheckoutSession,
  CheckoutSessionDetail,
  RecentEventsResponse,
  RecentSessionsResponse,
} from '../types/history'

export class ApiError extends Error {
  readonly statusCode: number | undefined

  constructor(
    message: string,
    statusCode?: number,
  ) {
    super(message)
    this.name = 'ApiError'
    this.statusCode = statusCode
  }
}

type JsonValidator<T> = (value: unknown) => value is T

interface JsonRequestOptions {
  method: 'GET' | 'POST'
  signal?: AbortSignal
  acceptedStatuses?: readonly number[]
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isNonNegativeNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0
}

function isNonNegativeInteger(value: unknown): value is number {
  return Number.isInteger(value) && typeof value === 'number' && value >= 0
}

function isPositiveInteger(value: unknown): value is number {
  return Number.isInteger(value) && typeof value === 'number' && value >= 1
}

function isTimestamp(value: unknown): value is string {
  return typeof value === 'string' && Number.isFinite(Date.parse(value))
}

function isCartEventType(value: unknown): value is CartEventType {
  return value === 'ADD' || value === 'REMOVE' || value === 'RESET'
}

function isHealthResponse(value: unknown): value is HealthResponse {
  if (!isRecord(value)) {
    return false
  }

  return (
    value.status === 'ok' && isNonNegativeNumber(value.uptime_seconds)
  )
}

function isApplicationState(value: unknown): value is ApplicationState {
  return (
    value === 'initializing' ||
    value === 'running' ||
    value === 'stopping' ||
    value === 'stopped' ||
    value === 'error'
  )
}

function isReadinessComponentStatus(
  value: unknown,
): value is ReadinessComponentStatus {
  return (
    value === 'initializing' ||
    value === 'ready' ||
    value === 'unavailable' ||
    value === 'disabled'
  )
}

function isReadinessResponse(value: unknown): value is ReadinessResponse {
  if (
    !isRecord(value) ||
    (value.status !== 'ready' && value.status !== 'not_ready') ||
    !isApplicationState(value.application_state) ||
    !isRecord(value.components)
  ) {
    return false
  }

  return Object.values(value.components).every(isReadinessComponentStatus)
}

const integerMetricNames = [
  'frames_processed_total',
  'dropped_frames_total',
  'detections_total',
  'active_tracks',
  'checkout_enter_events_total',
  'checkout_exit_events_total',
  'cart_additions_total',
  'cart_removals_total',
  'cart_resets_total',
  'current_cart_items',
  'current_cart_total',
  'camera_errors_total',
  'persistence_errors_total',
] as const satisfies readonly (keyof MetricsResponse)[]

const numericMetricNames = [
  'inference_latency_ms',
  'frame_processing_latency_ms',
  'current_fps',
  'uptime_seconds',
] as const satisfies readonly (keyof MetricsResponse)[]

export function isMetricsResponse(value: unknown): value is MetricsResponse {
  if (!isRecord(value)) {
    return false
  }

  return (
    integerMetricNames.every((name) => isNonNegativeInteger(value[name])) &&
    numericMetricNames.every((name) => isNonNegativeNumber(value[name]))
  )
}

function isCartItem(value: unknown): value is CartItem {
  if (!isRecord(value)) {
    return false
  }

  return (
    typeof value.product_id === 'string' &&
    typeof value.product_name === 'string' &&
    typeof value.quantity === 'number' &&
    Number.isInteger(value.quantity) &&
    value.quantity >= 1 &&
    isNonNegativeInteger(value.unit_price) &&
    isNonNegativeInteger(value.subtotal)
  )
}

export function isCartResponse(value: unknown): value is CartResponse {
  if (!isRecord(value)) {
    return false
  }

  return (
    Array.isArray(value.items) &&
    value.items.every(isCartItem) &&
    isNonNegativeInteger(value.total_quantity) &&
    isNonNegativeInteger(value.total)
  )
}

function isCartResetResponse(value: unknown): value is CartResetResponse {
  if (!isRecord(value)) {
    return false
  }

  return (
    typeof value.status === 'string' &&
    isNonNegativeInteger(value.removed_track_count) &&
    isCartResponse(value.cart)
  )
}

export function isCheckoutEvent(value: unknown): value is CheckoutEvent {
  if (
    !isRecord(value) ||
    !isPositiveInteger(value.id) ||
    !isPositiveInteger(value.session_id) ||
    !isTimestamp(value.timestamp) ||
    !isCartEventType(value.event_type)
  ) {
    return false
  }

  if (value.event_type === 'RESET') {
    return (
      value.track_id === null &&
      value.product_id === null &&
      value.unit_price === null
    )
  }

  return (
    isPositiveInteger(value.track_id) &&
    typeof value.product_id === 'string' &&
    value.product_id.length > 0 &&
    isNonNegativeInteger(value.unit_price)
  )
}

function isRecentEventsResponse(value: unknown): value is RecentEventsResponse {
  return (
    isRecord(value) &&
    Array.isArray(value.events) &&
    value.events.every(isCheckoutEvent) &&
    isPositiveInteger(value.limit) &&
    value.limit <= 200
  )
}

function isCheckoutSession(value: unknown): value is CheckoutSession {
  if (
    !isRecord(value) ||
    !isPositiveInteger(value.id) ||
    !isTimestamp(value.started_at)
  ) {
    return false
  }

  if (value.ended_at === null) {
    return value.final_total === null
  }

  return isTimestamp(value.ended_at) && isNonNegativeInteger(value.final_total)
}

function isRecentSessionsResponse(
  value: unknown,
): value is RecentSessionsResponse {
  return (
    isRecord(value) &&
    Array.isArray(value.sessions) &&
    value.sessions.every(isCheckoutSession) &&
    isPositiveInteger(value.limit) &&
    value.limit <= 100
  )
}

function isCheckoutSessionDetail(
  value: unknown,
): value is CheckoutSessionDetail {
  const events = isRecord(value) ? value.events : undefined
  return (
    isCheckoutSession(value) &&
    Array.isArray(events) &&
    events.every(isCheckoutEvent)
  )
}

function requireIntegerInRange(
  value: number,
  minimum: number,
  maximum: number,
  name: string,
): void {
  if (!Number.isInteger(value) || value < minimum || value > maximum) {
    throw new RangeError(`${name} must be between ${minimum} and ${maximum}.`)
  }
}

async function requestJson<T>(
  path: string,
  options: JsonRequestOptions,
  validator: JsonValidator<T>,
  invalidDataMessage: string,
): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${appConfig.apiBaseUrl}${path}`, {
      method: options.method,
      headers: { Accept: 'application/json' },
      signal: options.signal,
    })
  } catch (error: unknown) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error
    }
    throw new ApiError('Unable to connect to backend.')
  }

  const statusAccepted = options.acceptedStatuses?.includes(response.status)
  if (!response.ok && !statusAccepted) {
    throw new ApiError('Backend request failed.', response.status)
  }

  let payload: unknown
  try {
    payload = await response.json()
  } catch {
    throw new ApiError(
      invalidDataMessage,
      response.ok ? undefined : response.status,
    )
  }

  if (!validator(payload)) {
    throw new ApiError(
      invalidDataMessage,
      response.ok ? undefined : response.status,
    )
  }

  return payload
}

export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return requestJson(
    '/health',
    { method: 'GET', signal },
    isHealthResponse,
    'Backend returned invalid health data.',
  )
}

export function getReadiness(signal?: AbortSignal): Promise<ReadinessResponse> {
  return requestJson(
    '/ready',
    { method: 'GET', signal, acceptedStatuses: [503] },
    isReadinessResponse,
    'Backend returned invalid readiness data.',
  )
}

export function getMetrics(signal?: AbortSignal): Promise<MetricsResponse> {
  return requestJson(
    '/api/v1/metrics',
    { method: 'GET', signal },
    isMetricsResponse,
    'Backend returned invalid metrics data.',
  )
}

export function getCart(signal?: AbortSignal): Promise<CartResponse> {
  return requestJson(
    '/api/v1/cart',
    { method: 'GET', signal },
    isCartResponse,
    'Backend returned invalid cart data.',
  )
}

export function resetCart(signal?: AbortSignal): Promise<CartResetResponse> {
  return requestJson(
    '/api/v1/cart/reset',
    { method: 'POST', signal },
    isCartResetResponse,
    'Backend returned invalid cart reset data.',
  )
}

export function getRecentEvents(
  limit = 8,
  signal?: AbortSignal,
): Promise<RecentEventsResponse> {
  requireIntegerInRange(limit, 1, 200, 'Event limit')
  return requestJson(
    `/api/v1/events?limit=${limit}`,
    { method: 'GET', signal },
    isRecentEventsResponse,
    'Backend returned invalid checkout event data.',
  )
}

export function getSessions(
  limit = 20,
  signal?: AbortSignal,
): Promise<RecentSessionsResponse> {
  requireIntegerInRange(limit, 1, 100, 'Session limit')
  return requestJson(
    `/api/v1/sessions?limit=${limit}`,
    { method: 'GET', signal },
    isRecentSessionsResponse,
    'Backend returned invalid checkout session data.',
  )
}

export function getSessionById(
  sessionId: number,
  signal?: AbortSignal,
): Promise<CheckoutSessionDetail> {
  requireIntegerInRange(sessionId, 1, Number.MAX_SAFE_INTEGER, 'Session ID')
  return requestJson(
    `/api/v1/sessions/${sessionId}`,
    { method: 'GET', signal },
    isCheckoutSessionDetail,
    'Backend returned invalid checkout session data.',
  )
}
