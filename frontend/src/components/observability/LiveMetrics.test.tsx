import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { LiveMetrics } from './LiveMetrics'

afterEach(() => vi.unstubAllGlobals())

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

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), { status: 200 })
}

describe('LiveMetrics', () => {
  it('shows a contained loading state', () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(() => new Promise<Response>(() => undefined)),
    )

    render(<LiveMetrics />)

    expect(screen.getByText('Loading live metrics...')).toBeVisible()
  })

  it('renders the compact backend-supported metric set', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(metricsResponse)),
    )

    render(<LiveMetrics />)

    expect(await screen.findByText('28.2')).toBeVisible()
    expect(screen.getByText('31.4 ms')).toBeVisible()
    expect(screen.getByText('Active tracks')).toBeVisible()
    expect(screen.getByText('8,421')).toBeVisible()
    expect(screen.getByText('Dropped frames')).toBeVisible()
  })

  it('shows a retryable local error without crashing its card', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockRejectedValueOnce(new TypeError('offline'))
      .mockResolvedValueOnce(jsonResponse(metricsResponse))
    vi.stubGlobal('fetch', fetchMock)

    render(<LiveMetrics />)

    expect(await screen.findByText('Unable to load metrics.')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Retry metrics' }))
    expect(await screen.findByText('28.2')).toBeVisible()
  })
})
