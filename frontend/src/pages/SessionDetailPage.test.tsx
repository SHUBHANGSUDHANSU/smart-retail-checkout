import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { SessionDetailPage } from './SessionDetailPage'

afterEach(() => vi.unstubAllGlobals())

function renderSessionDetail(path = '/sessions/21') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/sessions/:sessionId" element={<SessionDetailPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), { status })
}

const sessionDetail = {
  id: 21,
  started_at: '2026-08-25T16:00:00Z',
  ended_at: '2026-08-25T16:30:00Z',
  final_total: 315,
  events: [
    {
      id: 1,
      session_id: 21,
      timestamp: '2026-08-25T16:04:03Z',
      track_id: 7,
      product_id: 'water_bottle',
      event_type: 'ADD',
      unit_price: 40,
    },
    {
      id: 2,
      session_id: 21,
      timestamp: '2026-08-25T16:05:03Z',
      track_id: null,
      product_id: null,
      event_type: 'RESET',
      unit_price: null,
    },
  ],
}

describe('SessionDetailPage', () => {
  it('shows a contained loading state', () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(() => new Promise<Response>(() => undefined)),
    )

    renderSessionDetail()

    expect(screen.getByRole('heading', { name: 'Session #21' })).toBeVisible()
    expect(screen.getByText('Loading checkout session...')).toBeVisible()
  })

  it('renders session metadata and persisted event history', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(sessionDetail)),
    )

    renderSessionDetail()

    expect(await screen.findByText('₹315')).toBeVisible()
    expect(screen.getByText('Completed')).toBeVisible()
    expect(screen.getByRole('heading', { name: 'Event History' })).toBeVisible()
    expect(screen.getByText('Water Bottle')).toBeVisible()
    expect(screen.getByText('Added to cart')).toBeVisible()
    expect(screen.getByText('Cart reset')).toBeVisible()
    expect(screen.getAllByRole('time')[0]).toHaveAttribute(
      'datetime',
      '2026-08-25T16:00:00Z',
    )
    expect(screen.getByRole('link', { name: 'Back to Sessions' })).toHaveAttribute(
      'href',
      '/sessions',
    )
  })

  it('renders a clean not-found state for backend 404 responses', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(
        jsonResponse(
          {
            code: 'session_not_found',
            message: 'Checkout session 21 was not found.',
          },
          404,
        ),
      ),
    )

    renderSessionDetail()

    expect(await screen.findByText('Session not found')).toBeVisible()
    expect(screen.queryByText('Checkout session 21 was not found.')).not.toBeInTheDocument()
  })

  it('handles invalid route identifiers without making an API request', () => {
    const fetchMock = vi.fn<typeof fetch>()
    vi.stubGlobal('fetch', fetchMock)

    renderSessionDetail('/sessions/not-a-number')

    expect(screen.getByText('Session not found')).toBeVisible()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('shows a retry action for a recoverable detail failure', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        jsonResponse(
          {
            code: 'persistence_unavailable',
            message: 'Checkout history is temporarily unavailable.',
          },
          503,
        ),
      )
      .mockResolvedValueOnce(jsonResponse(sessionDetail))
    vi.stubGlobal('fetch', fetchMock)

    renderSessionDetail()

    expect(
      await screen.findByText('Unable to load checkout session.'),
    ).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Retry session' }))
    expect(await screen.findByText('₹315')).toBeVisible()
  })

  it('aborts a pending detail request on navigation away', () => {
    let signal: AbortSignal | undefined
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>((_input, init) => {
        signal = init?.signal ?? undefined
        return new Promise<Response>(() => undefined)
      }),
    )

    const view = renderSessionDetail()
    view.unmount()

    expect(signal?.aborted).toBe(true)
  })
})
