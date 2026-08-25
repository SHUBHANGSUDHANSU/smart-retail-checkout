import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { DashboardPage } from './DashboardPage'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('DashboardPage backend connection', () => {
  it('shows a loading state while health is pending', () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(() => new Promise<Response>(() => undefined)),
    )

    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    )

    expect(screen.getByText('Checking backend...')).toBeInTheDocument()
  })

  it('shows Backend Connected after a successful health response', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockImplementation((input) => {
      const url = String(input)
      const payload = url.endsWith('/api/v1/cart')
        ? { items: [], total_quantity: 0, total: 0 }
        : { status: 'ok', uptime_seconds: 4.2 }
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

    expect(await screen.findByText('Backend Connected')).toBeInTheDocument()
    expect(await screen.findByText('Cart is empty')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(2)
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

    expect(await screen.findByText('Backend Unavailable')).toBeInTheDocument()
    expect(screen.getByText('Unable to connect to backend.')).toBeInTheDocument()
  })

  it('aborts the pending health request when unmounted', () => {
    const request = { signal: null as AbortSignal | null }
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>((_input, init) => {
        request.signal = init?.signal ?? null
        return new Promise<Response>(() => undefined)
      }),
    )

    const view = render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    )
    expect(request.signal).not.toBeNull()

    view.unmount()

    expect(request.signal?.aborted).toBe(true)
  })
})
