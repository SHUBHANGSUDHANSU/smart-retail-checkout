import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { getCart, resetCart } from '../services/api'
import type { CartResetResponse, CartResponse } from '../types/cart'
import { CART_POLL_INTERVAL_MS, useCart } from './useCart'

vi.mock('../services/api', () => ({
  getCart: vi.fn(),
  resetCart: vi.fn(),
}))

const emptyCart: CartResponse = {
  items: [],
  total_quantity: 0,
  total: 0,
}

const populatedCart: CartResponse = {
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

const getCartMock = vi.mocked(getCart)
const resetCartMock = vi.mocked(resetCart)

beforeEach(() => {
  getCartMock.mockReset()
  resetCartMock.mockReset()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useCart', () => {
  it('loads immediately and polls again without flashing initial loading', async () => {
    vi.useFakeTimers()
    getCartMock.mockResolvedValue(emptyCart)

    const view = renderHook(() => useCart())

    expect(view.result.current.isInitialLoading).toBe(true)
    await act(async () => {
      await Promise.resolve()
    })
    expect(view.result.current.cart).toEqual(emptyCart)
    expect(view.result.current.isInitialLoading).toBe(false)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(CART_POLL_INTERVAL_MS)
    })
    expect(getCartMock).toHaveBeenCalledTimes(2)
    expect(view.result.current.isInitialLoading).toBe(false)

    view.unmount()
    await vi.advanceTimersByTimeAsync(CART_POLL_INTERVAL_MS)
    expect(getCartMock).toHaveBeenCalledTimes(2)
  })

  it('shares an in-flight refresh instead of starting overlapping reads', async () => {
    let resolveRequest: ((cart: CartResponse) => void) | undefined
    getCartMock.mockImplementation(
      () =>
        new Promise<CartResponse>((resolve) => {
          resolveRequest = resolve
        }),
    )

    const view = renderHook(() => useCart())
    let firstRefresh: Promise<void> | undefined
    let secondRefresh: Promise<void> | undefined
    act(() => {
      firstRefresh = view.result.current.refresh()
      secondRefresh = view.result.current.refresh()
    })

    expect(getCartMock).toHaveBeenCalledTimes(1)
    expect(firstRefresh).toBe(secondRefresh)

    await act(async () => {
      resolveRequest?.(emptyCart)
      await firstRefresh
    })
    view.unmount()
  })

  it('uses the backend reset result and reconciles with a fresh snapshot', async () => {
    getCartMock
      .mockResolvedValueOnce(populatedCart)
      .mockResolvedValueOnce(emptyCart)
    resetCartMock.mockResolvedValue({
      status: 'reset',
      removed_track_count: 2,
      cart: emptyCart,
    })

    const view = renderHook(() => useCart())
    await waitFor(() => expect(view.result.current.cart).toEqual(populatedCart))

    await act(async () => {
      await Promise.all([
        view.result.current.reset(),
        view.result.current.reset(),
      ])
    })

    expect(resetCartMock).toHaveBeenCalledTimes(1)
    expect(getCartMock).toHaveBeenCalledTimes(2)
    expect(view.result.current.cart).toEqual(emptyCart)
    expect(view.result.current.isResetting).toBe(false)
    view.unmount()
  })

  it('keeps failures local and exposes a retryable cart error', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    getCartMock.mockRejectedValue(new TypeError('network detail'))

    const view = renderHook(() => useCart())

    await waitFor(() => {
      expect(view.result.current.isInitialLoading).toBe(false)
      expect(view.result.current.error).toBe('Unable to load cart.')
    })
    expect(view.result.current.cart).toBeNull()
    view.unmount()
  })

  it('does not start reconciliation after unmounting during reset', async () => {
    let resolveReset: ((response: CartResetResponse) => void) | undefined
    getCartMock.mockResolvedValue(populatedCart)
    resetCartMock.mockImplementation(
      () =>
        new Promise<CartResetResponse>((resolve) => {
          resolveReset = resolve
        }),
    )

    const view = renderHook(() => useCart())
    await waitFor(() => expect(view.result.current.cart).toEqual(populatedCart))

    let resetRequest: Promise<boolean> | undefined
    act(() => {
      resetRequest = view.result.current.reset()
    })
    await waitFor(() => expect(resetCartMock).toHaveBeenCalledTimes(1))
    view.unmount()

    resolveReset?.({
      status: 'reset',
      removed_track_count: 2,
      cart: emptyCart,
    })
    await resetRequest

    expect(getCartMock).toHaveBeenCalledTimes(1)
  })
})
