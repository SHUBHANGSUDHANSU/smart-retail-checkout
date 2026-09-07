import { afterEach, describe, expect, it, vi } from 'vitest'

import { appConfig } from '../config'
import { ApiError, getMetrics, getReadiness } from './api'

afterEach(() => {
  vi.unstubAllGlobals()
})

const readyResponse = {
  status: 'ready',
  application_state: 'running',
  components: {
    core_services: 'ready',
    model: 'ready',
    camera: 'ready',
    vision_pipeline: 'ready',
    database: 'ready',
  },
}

const metricsResponse = {
  frames_processed_total: 8421,
  dropped_frames_total: 2,
  detections_total: 4391,
  active_tracks: 3,
  inference_latency_ms: 31.4,
  frame_processing_latency_ms: 38.8,
  current_fps: 28.2,
  checkout_enter_events_total: 7,
  checkout_exit_events_total: 2,
  cart_additions_total: 7,
  cart_removals_total: 2,
  cart_resets_total: 1,
  current_cart_items: 5,
  current_cart_total: 250,
  uptime_seconds: 8040,
  camera_errors_total: 1,
  persistence_errors_total: 0,
}

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('getReadiness', () => {
  it('returns a typed ready response', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(jsonResponse(readyResponse))
    vi.stubGlobal('fetch', fetchMock)

    await expect(getReadiness()).resolves.toEqual(readyResponse)
    expect(fetchMock).toHaveBeenCalledWith(
      `${appConfig.apiBaseUrl}/ready`,
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('preserves a valid not-ready response returned with HTTP 503', async () => {
    const notReady = {
      ...readyResponse,
      status: 'not_ready',
      components: { ...readyResponse.components, camera: 'unavailable' },
    }
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(notReady, 503)),
    )

    await expect(getReadiness()).resolves.toEqual(notReady)
  })

  it('rejects malformed readiness data', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(
        jsonResponse({
          ...readyResponse,
          components: { camera: 'mysterious' },
        }),
      ),
    )

    await expect(getReadiness()).rejects.toEqual(
      expect.objectContaining({
        message: 'Backend returned invalid readiness data.',
      }),
    )
  })

  it('rejects an unstructured HTTP 503 response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(new Response('unavailable', { status: 503 })),
    )

    await expect(getReadiness()).rejects.toEqual(
      expect.objectContaining({ statusCode: 503 }),
    )
  })
})

describe('getMetrics', () => {
  it('returns every metric from one backend snapshot', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(jsonResponse(metricsResponse))
    vi.stubGlobal('fetch', fetchMock)

    await expect(getMetrics()).resolves.toEqual(metricsResponse)
    expect(fetchMock).toHaveBeenCalledWith(
      `${appConfig.apiBaseUrl}/api/v1/metrics`,
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('rejects incomplete or non-finite metric snapshots', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(
        jsonResponse({ ...metricsResponse, current_fps: 'unknown' }),
      ),
    )

    const request = getMetrics()
    await expect(request).rejects.toBeInstanceOf(ApiError)
    await expect(request).rejects.toThrow('invalid metrics data')
  })
})
