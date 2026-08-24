import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, getHealth } from './api'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('getHealth', () => {
  it('returns the typed backend liveness response', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ status: 'ok', uptime_seconds: 12.5 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(getHealth()).resolves.toEqual({
      status: 'ok',
      uptime_seconds: 12.5,
    })
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/health',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('rejects a non-success response without exposing its body', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(
        new Response('internal detail', { status: 503 }),
      ),
    )

    const request = getHealth()
    await expect(request).rejects.toBeInstanceOf(ApiError)
    await expect(request).rejects.toEqual(
      expect.objectContaining({
        message: 'Backend request failed.',
        statusCode: 503,
      }),
    )
  })

  it('rejects malformed liveness data', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(
        new Response(JSON.stringify({ status: 'ok', uptime_seconds: 'fast' }), {
          status: 200,
        }),
      ),
    )

    await expect(getHealth()).rejects.toThrow('invalid health data')
  })
})
