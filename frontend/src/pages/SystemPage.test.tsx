import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ReadinessResponse } from '../types/api'
import { SystemPage } from './SystemPage'

afterEach(() => vi.unstubAllGlobals())

const healthResponse = { status: 'ok', uptime_seconds: 8040 }
const readinessResponse: ReadinessResponse = {
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

function responseFor(
  url: string,
  readiness: ReadinessResponse = readinessResponse,
): Response {
  const payload = url.endsWith('/health')
    ? healthResponse
    : url.endsWith('/ready')
      ? readiness
      : metricsResponse
  const status = url.endsWith('/ready') && readiness.status === 'not_ready' ? 503 : 200
  return new Response(JSON.stringify(payload), { status })
}

describe('SystemPage', () => {
  it('renders liveness, readiness components, and operational metrics', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>((input) =>
        Promise.resolve(responseFor(String(input))),
      ),
    )

    render(<SystemPage />)

    expect(screen.getByRole('heading', { name: 'System Health' })).toBeVisible()
    expect(
      await screen.findByText(/Application process is responding\./),
    ).toBeVisible()
    expect(screen.getByText('Ready to process checkout work.')).toBeVisible()
    expect(screen.getByText('Core Services')).toBeVisible()
    expect(screen.getByText('Vision Pipeline')).toBeVisible()
    expect(await screen.findByText('8,421')).toBeVisible()
    expect(screen.getByText('4,391')).toBeVisible()
    expect(screen.getByText('2h 14m')).toBeVisible()
    expect(screen.getByText('₹250')).toBeVisible()
  })

  it('renders structured HTTP 503 readiness as a degraded state', async () => {
    const notReady: ReadinessResponse = {
      ...readinessResponse,
      status: 'not_ready',
      components: { ...readinessResponse.components, camera: 'unavailable' },
    }
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>((input) =>
        Promise.resolve(responseFor(String(input), notReady)),
      ),
    )

    render(<SystemPage />)

    expect(await screen.findByText('Not ready for checkout work.')).toBeVisible()
    expect(screen.getByText('Camera')).toBeVisible()
    expect(screen.getByText('Unavailable')).toBeVisible()
  })

  it('shows retry controls when the backend is unavailable', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockRejectedValueOnce(new TypeError('offline'))
      .mockRejectedValueOnce(new TypeError('offline'))
      .mockRejectedValueOnce(new TypeError('offline'))
      .mockImplementation((input) => Promise.resolve(responseFor(String(input))))
    vi.stubGlobal('fetch', fetchMock)

    render(<SystemPage />)

    expect(await screen.findByText('Liveness unavailable.')).toBeVisible()
    expect(screen.getByText('Readiness unavailable.')).toBeVisible()
    expect(screen.getByText('Unable to load metrics.')).toBeVisible()

    fireEvent.click(screen.getByRole('button', { name: 'Retry system status' }))
    expect(
      await screen.findByText(/Application process is responding\./),
    ).toBeVisible()
  })

  it('handles an empty component map without inventing dependencies', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>((input) =>
        Promise.resolve(
          responseFor(String(input), { ...readinessResponse, components: {} }),
        ),
      ),
    )

    render(<SystemPage />)

    expect(
      await screen.findByText('No component readiness data available.'),
    ).toBeVisible()
  })
})
