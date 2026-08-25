import { appConfig } from '../config'
import type { HealthResponse } from '../types/api'
import type { CartItem, CartResetResponse, CartResponse } from '../types/cart'

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
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isNonNegativeInteger(value: unknown): value is number {
  return Number.isInteger(value) && typeof value === 'number' && value >= 0
}

function isHealthResponse(value: unknown): value is HealthResponse {
  if (!isRecord(value)) {
    return false
  }

  return (
    typeof value.status === 'string' &&
    typeof value.uptime_seconds === 'number' &&
    Number.isFinite(value.uptime_seconds) &&
    value.uptime_seconds >= 0
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

function isCartResponse(value: unknown): value is CartResponse {
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

  if (!response.ok) {
    throw new ApiError('Backend request failed.', response.status)
  }

  let payload: unknown
  try {
    payload = await response.json()
  } catch {
    throw new ApiError(invalidDataMessage)
  }

  if (!validator(payload)) {
    throw new ApiError(invalidDataMessage)
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
