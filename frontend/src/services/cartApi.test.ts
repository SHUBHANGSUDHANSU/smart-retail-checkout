import { afterEach, describe, expect, it, vi } from 'vitest'

import { appConfig } from '../config'
import { ApiError, getCart, resetCart } from './api'

const populatedCart = {
  items: [
    {
      product_id: 'bottle',
      product_name: 'Water Bottle',
      quantity: 2,
      unit_price: 40,
      subtotal: 80,
    },
  ],
  total_quantity: 2,
  total: 80,
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('cart API', () => {
  it('returns the backend aggregated cart snapshot', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify(populatedCart), { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(getCart()).resolves.toEqual(populatedCart)
    expect(fetchMock).toHaveBeenCalledWith(
      `${appConfig.apiBaseUrl}/api/v1/cart`,
      expect.objectContaining({
        method: 'GET',
        headers: { Accept: 'application/json' },
      }),
    )
  })

  it('resets the shared backend cart and returns its resulting snapshot', async () => {
    const resetResponse = {
      status: 'reset',
      removed_track_count: 2,
      cart: { items: [], total_quantity: 0, total: 0 },
    }
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        new Response(JSON.stringify(resetResponse), { status: 200 }),
      )
    vi.stubGlobal('fetch', fetchMock)

    await expect(resetCart()).resolves.toEqual(resetResponse)
    expect(fetchMock).toHaveBeenCalledWith(
      `${appConfig.apiBaseUrl}/api/v1/cart/reset`,
      expect.objectContaining({
        method: 'POST',
        headers: { Accept: 'application/json' },
      }),
    )
  })

  it('rejects malformed cart data with a safe API error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(
        new Response(
          JSON.stringify({
            items: [{ ...populatedCart.items[0], quantity: 'two' }],
            total_quantity: 2,
            total: 80,
          }),
          { status: 200 },
        ),
      ),
    )

    const request = getCart()
    await expect(request).rejects.toBeInstanceOf(ApiError)
    await expect(request).rejects.toMatchObject({
      message: 'Backend returned invalid cart data.',
      statusCode: undefined,
    })
  })
})
