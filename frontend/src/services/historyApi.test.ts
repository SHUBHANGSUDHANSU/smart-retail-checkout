import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  ApiError,
  getRecentEvents,
  getSessionById,
  getSessions,
} from './api'

afterEach(() => vi.unstubAllGlobals())

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const event = {
  id: 12,
  session_id: 4,
  timestamp: '2026-08-25T16:44:03Z',
  track_id: 7,
  product_id: 'bottle',
  event_type: 'ADD',
  unit_price: 40,
}

const session = {
  id: 4,
  started_at: '2026-08-25T16:40:00Z',
  ended_at: '2026-08-25T16:45:00Z',
  final_total: 125,
}

describe('checkout history API', () => {
  it('loads recent events with the requested bounded limit', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      jsonResponse({ events: [event], limit: 8 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(getRecentEvents(8)).resolves.toEqual({
      events: [event],
      limit: 8,
    })
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/events?limit=8',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('rejects unknown event types instead of trusting malformed history', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(
        jsonResponse({
          events: [{ ...event, event_type: 'CART_ADD_INTERNAL_V2' }],
          limit: 8,
        }),
      ),
    )

    await expect(getRecentEvents(8)).rejects.toThrow(
      'Backend returned invalid checkout event data.',
    )
  })

  it('loads recent session summaries using the real limit query', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      jsonResponse({ sessions: [session], limit: 20 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(getSessions(20)).resolves.toEqual({
      sessions: [session],
      limit: 20,
    })
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/sessions?limit=20',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('loads one session with its insertion-ordered event history', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      jsonResponse({ ...session, events: [event] }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(getSessionById(4)).resolves.toEqual({
      ...session,
      events: [event],
    })
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/sessions/4',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('preserves a missing session response as an API error with status 404', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(
        jsonResponse(
          {
            code: 'session_not_found',
            message: 'Checkout session 999 was not found.',
          },
          404,
        ),
      ),
    )

    const request = getSessionById(999)

    await expect(request).rejects.toBeInstanceOf(ApiError)
    await expect(request).rejects.toMatchObject({ statusCode: 404 })
  })

  it('rejects invalid history identifiers and limits before making a request', () => {
    const fetchMock = vi.fn<typeof fetch>()
    vi.stubGlobal('fetch', fetchMock)

    expect(() => getRecentEvents(0)).toThrow(RangeError)
    expect(() => getSessions(101)).toThrow(RangeError)
    expect(() => getSessionById(-1)).toThrow(RangeError)
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
