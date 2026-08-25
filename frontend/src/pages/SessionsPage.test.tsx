import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { SessionsPage } from './SessionsPage'

afterEach(() => vi.unstubAllGlobals())

function renderSessionsPage() {
  return render(
    <MemoryRouter>
      <SessionsPage />
    </MemoryRouter>,
  )
}

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), { status })
}

const sessionsResponse = {
  sessions: [
    {
      id: 22,
      started_at: '2026-08-25T17:00:00Z',
      ended_at: null,
      final_total: null,
    },
    {
      id: 21,
      started_at: '2026-08-25T16:00:00Z',
      ended_at: '2026-08-25T16:30:00Z',
      final_total: 315,
    },
  ],
  limit: 20,
}

describe('SessionsPage', () => {
  it('renders active and completed persisted sessions', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(sessionsResponse)),
    )

    renderSessionsPage()

    expect(
      await screen.findByRole('link', { name: 'Session #22' }),
    ).toHaveAttribute('href', '/sessions/22')
    expect(screen.getByRole('link', { name: 'Session #21' })).toHaveAttribute(
      'href',
      '/sessions/21',
    )
    expect(screen.getByRole('columnheader', { name: 'Started' })).toBeVisible()
    expect(screen.getByText('Active')).toBeVisible()
    expect(screen.getByText('Completed')).toBeVisible()
    expect(screen.getByText('₹315')).toBeVisible()
  })

  it('shows an empty history state without fabricating sessions', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(
        jsonResponse({ sessions: [], limit: 20 }),
      ),
    )

    renderSessionsPage()

    expect(await screen.findByText('No checkout sessions yet')).toBeVisible()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('shows a safe failure state and retries the sessions request', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockRejectedValueOnce(new TypeError('private database detail'))
      .mockResolvedValueOnce(jsonResponse(sessionsResponse))
    vi.stubGlobal('fetch', fetchMock)

    renderSessionsPage()

    expect(
      await screen.findByText('Unable to load checkout sessions.'),
    ).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Retry sessions' }))
    expect(
      await screen.findByRole('link', { name: 'Session #21' }),
    ).toBeVisible()
    expect(screen.queryByText('private database detail')).not.toBeInTheDocument()
  })

  it('aborts a pending sessions request on navigation away', () => {
    let signal: AbortSignal | undefined
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>((_input, init) => {
        signal = init?.signal ?? undefined
        return new Promise<Response>(() => undefined)
      }),
    )

    const view = renderSessionsPage()
    view.unmount()

    expect(signal?.aborted).toBe(true)
  })
})
