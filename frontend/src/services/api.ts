import { appConfig } from '../config'
import type { HealthResponse } from '../types/api'

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

function isHealthResponse(value: unknown): value is HealthResponse {
  if (typeof value !== 'object' || value === null) {
    return false
  }

  const record = value as Record<string, unknown>
  return (
    typeof record.status === 'string' &&
    typeof record.uptime_seconds === 'number' &&
    Number.isFinite(record.uptime_seconds) &&
    record.uptime_seconds >= 0
  )
}

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  let response: Response
  try {
    response = await fetch(`${appConfig.apiBaseUrl}/health`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal,
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
    throw new ApiError('Backend returned invalid health data.')
  }

  if (!isHealthResponse(payload)) {
    throw new ApiError('Backend returned invalid health data.')
  }

  return payload
}
