import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { DashboardPage } from './DashboardPage'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('DashboardPage backend connection', () => {
  it('places operational status before checkout details in reading order', () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(() => new Promise<Response>(() => undefined)),
    )

    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    )

    const headings = screen.getAllByRole('heading', { level: 2 })
    expect(headings.map((heading) => heading.textContent)).toEqual([
      'System Status',
      'Current Cart',
      'Recent Events',
      'Live Metrics',
    ])
  })

  it('shows contained loading states while observability is pending', () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(() => new Promise<Response>(() => undefined)),
    )

    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    )

    expect(screen.getByText('Loading live metrics...')).toBeInTheDocument()
    expect(screen.getAllByText('Loading')).toHaveLength(2)
  })

  it('shows live health, readiness, cart, events, and metrics data', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockImplementation((input) => {
      const url = String(input)
      const payload = url.endsWith('/api/v1/cart')
        ? { items: [], total_quantity: 0, total: 0 }
        : url.includes('/api/v1/events')
          ? { events: [], limit: 8 }
          : url.endsWith('/health')
            ? { status: 'ok', uptime_seconds: 4.2 }
            : url.endsWith('/ready')
              ? {
                  status: 'ready',
                  application_state: 'running',
                  components: { camera: 'ready', database: 'ready' },
                }
              : {
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
      return Promise.resolve(
        new Response(JSON.stringify(payload), { status: 200 }),
      )
    })
    vi.stubGlobal('fetch', fetchMock)

    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    )

    expect(await screen.findByText('Healthy')).toBeInTheDocument()
    expect(screen.getAllByText('Ready')).toHaveLength(3)
    expect(await screen.findByText('28.2')).toBeInTheDocument()
    expect(await screen.findByText('Cart is empty')).toBeInTheDocument()
    expect(await screen.findByText('No checkout events yet')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(5)
  })

  it('shows a friendly unavailable state when fetch fails', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockRejectedValue(new TypeError('Failed to fetch')),
    )

    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    )

    expect(await screen.findAllByText('Unavailable')).toHaveLength(2)
    expect(
      screen.getByText('Some status data could not be refreshed.'),
    ).toBeInTheDocument()
  })

  it('aborts all pending dashboard requests when unmounted', () => {
    const signals: AbortSignal[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>((_input, init) => {
        if (init?.signal) signals.push(init.signal)
        return new Promise<Response>(() => undefined)
      }),
    )

    const view = render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    )
    expect(signals).toHaveLength(5)

    view.unmount()

    expect(signals.every((signal) => signal.aborted)).toBe(true)
  })
})
