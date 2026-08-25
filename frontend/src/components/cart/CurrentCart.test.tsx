import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { getCart, resetCart } from '../../services/api'
import type { CartResetResponse, CartResponse } from '../../types/cart'
import { CurrentCart } from './CurrentCart'

vi.mock('../../services/api', () => ({
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
    {
      product_id: 'apple',
      product_name: 'Apple',
      quantity: 1,
      unit_price: 45,
      subtotal: 45,
    },
  ],
  total_quantity: 3,
  total: 125,
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

describe('CurrentCart', () => {
  it('shows a contained loading state while the first request is pending', () => {
    getCartMock.mockImplementation(
      () => new Promise<CartResponse>(() => undefined),
    )

    render(<CurrentCart />)

    expect(screen.getByRole('heading', { name: 'Current Cart' })).toBeVisible()
    expect(screen.getByText('Loading cart...')).toBeVisible()
  })

  it('renders aggregated server items and server-calculated amounts', async () => {
    getCartMock.mockResolvedValue(populatedCart)

    render(<CurrentCart />)

    expect(await screen.findByText('Water Bottle')).toBeVisible()
    expect(screen.getByText('₹40 × 2')).toBeVisible()
    expect(screen.getByLabelText('Water Bottle subtotal')).toHaveTextContent('₹80')
    expect(screen.getByText('Apple')).toBeVisible()
    expect(screen.getByText('₹45 × 1')).toBeVisible()
    expect(screen.getByLabelText('Cart total')).toHaveTextContent('₹125')
  })

  it('shows guidance and disables reset when the backend cart is empty', async () => {
    getCartMock.mockResolvedValue(emptyCart)

    render(<CurrentCart />)

    expect(await screen.findByText('Cart is empty')).toBeVisible()
    expect(
      screen.getByText('Move a detected product into the checkout zone to add it.'),
    ).toBeVisible()
    expect(screen.getByRole('button', { name: 'Reset Cart' })).toBeDisabled()
  })

  it('shows a local error and retries without disturbing the dashboard', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    getCartMock
      .mockRejectedValueOnce(new TypeError('private network detail'))
      .mockResolvedValueOnce(emptyCart)

    render(<CurrentCart />)

    expect(await screen.findByText('Unable to load cart.')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))

    expect(await screen.findByText('Cart is empty')).toBeVisible()
    expect(screen.queryByText('private network detail')).not.toBeInTheDocument()
  })

  it('confirms reset, disables duplicate submission, and renders server state', async () => {
    let resolveReset: ((response: CartResetResponse) => void) | undefined
    getCartMock
      .mockResolvedValueOnce(populatedCart)
      .mockResolvedValueOnce(emptyCart)
    resetCartMock.mockImplementation(
      () =>
        new Promise<CartResetResponse>((resolve) => {
          resolveReset = resolve
        }),
    )

    render(<CurrentCart />)
    await screen.findByText('Water Bottle')

    fireEvent.click(screen.getByRole('button', { name: 'Reset Cart' }))
    expect(screen.getByRole('alertdialog')).toHaveTextContent('Reset current cart?')

    fireEvent.click(screen.getByRole('button', { name: 'Confirm reset cart' }))
    const submittingButton = screen.getByRole('button', {
      name: 'Resetting cart',
    })
    expect(submittingButton).toBeDisabled()
    fireEvent.click(submittingButton)
    await waitFor(() => expect(resetCartMock).toHaveBeenCalledTimes(1))

    resolveReset?.({
      status: 'reset',
      removed_track_count: 3,
      cart: emptyCart,
    })

    expect(await screen.findByText('Cart is empty')).toBeVisible()
    await waitFor(() => expect(getCartMock).toHaveBeenCalledTimes(2))
  })

  it('cancels reset without calling the backend', async () => {
    getCartMock.mockResolvedValue(populatedCart)

    render(<CurrentCart />)
    await screen.findByText('Water Bottle')

    const resetButton = screen.getByRole('button', { name: 'Reset Cart' })
    fireEvent.click(resetButton)
    fireEvent.click(screen.getByRole('button', { name: 'Cancel reset' }))

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    expect(resetCartMock).not.toHaveBeenCalled()
    await waitFor(() => expect(resetButton).toHaveFocus())
  })
})
