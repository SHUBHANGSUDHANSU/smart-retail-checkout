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
  const response = await fetch(`${appConfig.apiBaseUrl}/health`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
    signal,
  })
  if (!response.ok) {
    throw new ApiError('Backend request failed.', response.status)
  }

  const payload: unknown = await response.json()
  if (!isHealthResponse(payload)) {
    throw new ApiError('Backend returned invalid health data.')
  }

  return payload
}
