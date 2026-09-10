import { afterEach, describe, expect, it, vi } from 'vitest'

import { appConfig } from '../config'
import {
  ApiError,
  addDemoItem,
  getDemoManifest,
  getHealth,
  removeDemoItem,
} from './api'

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
      `${appConfig.apiBaseUrl}/health`,
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

  it('normalizes network failures to a safe connection error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockRejectedValue(new TypeError('Failed to fetch')),
    )

    await expect(getHealth()).rejects.toEqual(
      expect.objectContaining({
        message: 'Unable to connect to backend.',
        statusCode: undefined,
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

  it('normalizes invalid JSON to a safe invalid-data error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(
        new Response('not JSON', { status: 200 }),
      ),
    )

    await expect(getHealth()).rejects.toEqual(
      expect.objectContaining({
        message: 'Backend returned invalid health data.',
        statusCode: undefined,
      }),
    )
  })
})

describe('demo API', () => {
  const manifest = {
    mode: 'demo',
    vision_active: false,
    message: 'Using simulated checkout events. Computer vision is not active.',
    products: [
      {
        product_id: 'bottle',
        product_name: 'Water Bottle',
        unit_price: 40,
      },
    ],
  }

  it('discovers the enabled demo catalog', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify(manifest), { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(getDemoManifest()).resolves.toEqual(manifest)
    expect(fetchMock).toHaveBeenCalledWith(
      `${appConfig.apiBaseUrl}/api/v1/demo`,
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('uses encoded product paths for add and remove commands', async () => {
    const mutation = {
      status: 'added',
      track_id: 1_000_000,
      product: manifest.products[0],
      cart: {
        items: [
          {
            ...manifest.products[0],
            quantity: 1,
            subtotal: 40,
          },
        ],
        total_quantity: 1,
        total: 40,
      },
    }
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(mutation), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ ...mutation, status: 'removed' }),
          { status: 200 },
        ),
      )
    vi.stubGlobal('fetch', fetchMock)

    await addDemoItem('water bottle')
    await removeDemoItem('water bottle')

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      `${appConfig.apiBaseUrl}/api/v1/demo/items/water%20bottle`,
      expect.objectContaining({ method: 'POST' }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      `${appConfig.apiBaseUrl}/api/v1/demo/items/water%20bottle/remove`,
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('rejects malformed demo payloads', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(
        new Response(
          JSON.stringify({ ...manifest, vision_active: true }),
          { status: 200 },
        ),
      ),
    )

    await expect(getDemoManifest()).rejects.toThrow('invalid demo mode data')
  })
})
