import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { App } from '../App'
import { DemoModeProvider } from './DemoModeProvider'

const manifest = {
  mode: 'demo',
  vision_active: false,
  message: 'Using simulated checkout events. Computer vision is not active.',
  products: [
    { product_id: 'bottle', product_name: 'Water Bottle', unit_price: 40 },
  ],
}

function dashboardPayload(url: string): object {
  if (url.endsWith('/api/v1/demo')) return manifest
  if (url.endsWith('/api/v1/cart')) {
    return { items: [], total_quantity: 0, total: 0 }
  }
  if (url.includes('/api/v1/events')) return { events: [], limit: 8 }
  if (url.endsWith('/health')) return { status: 'ok', uptime_seconds: 1 }
  if (url.endsWith('/ready')) {
    return {
      status: 'ready',
      application_state: 'running',
      components: {
        camera: 'disabled',
        model: 'disabled',
        database: 'ready',
        vision_pipeline: 'disabled',
      },
    }
  }
  return {
    frames_processed_total: 0,
    dropped_frames_total: 0,
    detections_total: 0,
    active_tracks: 0,
    inference_latency_ms: 0,
    frame_processing_latency_ms: 0,
    current_fps: 0,
    checkout_enter_events_total: 0,
    checkout_exit_events_total: 0,
    cart_additions_total: 0,
    cart_removals_total: 0,
    cart_resets_total: 0,
    current_cart_items: 0,
    current_cart_total: 0,
    uptime_seconds: 1,
    camera_errors_total: 0,
    persistence_errors_total: 0,
  }
}

function renderDashboard() {
  return render(
    <MemoryRouter>
      <DemoModeProvider>
        <App />
      </DemoModeProvider>
    </MemoryRouter>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('DemoModeProvider', () => {
  it('keeps demo presentation absent when the conditional endpoint is missing', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>((input) => {
        const url = String(input)
        if (url.endsWith('/api/v1/demo')) {
          return Promise.resolve(new Response('{}', { status: 404 }))
        }
        return Promise.resolve(
          new Response(JSON.stringify(dashboardPayload(url)), { status: 200 }),
        )
      }),
    )

    renderDashboard()

    await waitFor(() =>
      expect(screen.queryByText('DEMO MODE')).not.toBeInTheDocument(),
    )
    expect(
      screen.queryByRole('heading', { name: 'Demo controls' }),
    ).not.toBeInTheDocument()
  })

  it('marks synthetic mode globally and runs backend demo commands', async () => {
    const fetchMock = vi.fn<typeof fetch>((input) => {
      const url = String(input)
      if (url.endsWith('/api/v1/demo/items/bottle')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              status: 'added',
              track_id: 1_000_000,
              product: manifest.products[0],
              cart: {
                items: [
                  {
                    product_id: 'bottle',
                    product_name: 'Water Bottle',
                    unit_price: 40,
                    quantity: 1,
                    subtotal: 40,
                  },
                ],
                total_quantity: 1,
                total: 40,
              },
            }),
            { status: 200 },
          ),
        )
      }
      return Promise.resolve(
        new Response(JSON.stringify(dashboardPayload(url)), { status: 200 }),
      )
    })
    vi.stubGlobal('fetch', fetchMock)

    renderDashboard()

    expect(await screen.findByText('DEMO MODE')).toBeInTheDocument()
    expect(
      screen.getByText(
        'Using simulated checkout events. Computer vision is not active.',
      ),
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Add Water Bottle' }))

    expect(await screen.findByText('Water Bottle added.')).toHaveAttribute(
      'role',
      'status',
    )
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/demo/items/bottle'),
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('disables controls while a command is pending and reports safe errors', async () => {
    let rejectCommand: ((reason: Error) => void) | undefined
    vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>((input) => {
        const url = String(input)
        if (url.endsWith('/api/v1/demo/items/bottle')) {
          return new Promise<Response>((_resolve, reject) => {
            rejectCommand = reject
          })
        }
        return Promise.resolve(
          new Response(JSON.stringify(dashboardPayload(url)), { status: 200 }),
        )
      }),
    )
    renderDashboard()
    const addButton = await screen.findByRole('button', {
      name: 'Add Water Bottle',
    })

    fireEvent.click(addButton)
    expect(addButton).toBeDisabled()
    rejectCommand?.(new TypeError('private network detail'))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Unable to update the demo cart.',
    )
    expect(addButton).toBeEnabled()
  })
})
