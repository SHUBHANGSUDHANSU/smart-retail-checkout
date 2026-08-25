import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { getRecentEvents } from '../../services/api'
import type { RecentEventsResponse } from '../../types/history'
import { EVENTS_POLL_INTERVAL_MS } from '../../hooks/useRecentEvents'
import { RecentEvents } from './RecentEvents'

vi.mock('../../services/api', () => ({
  getRecentEvents: vi.fn(),
}))

const response: RecentEventsResponse = {
  events: [
    {
      id: 1,
      session_id: 4,
      timestamp: '2026-08-25T22:14:03Z',
      track_id: 7,
      product_id: 'bottle',
      event_type: 'ADD',
      unit_price: 40,
    },
  ],
  limit: 8,
}

const getRecentEventsMock = vi.mocked(getRecentEvents)

beforeEach(() => {
  getRecentEventsMock.mockReset()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('RecentEvents', () => {
  it('shows a contained loading state during the first request', () => {
    getRecentEventsMock.mockImplementation(
      () => new Promise<RecentEventsResponse>(() => undefined),
    )

    render(<RecentEvents />)

    expect(screen.getByRole('heading', { name: 'Recent Events' })).toBeVisible()
    expect(screen.getByText('Loading checkout events...')).toBeVisible()
  })

  it('renders persisted checkout activity', async () => {
    getRecentEventsMock.mockResolvedValue(response)

    render(<RecentEvents />)

    expect(await screen.findByText('Bottle')).toBeVisible()
    expect(screen.getByText('Added to cart')).toBeVisible()
  })

  it('shows a truthful empty state', async () => {
    getRecentEventsMock.mockResolvedValue({ events: [], limit: 8 })

    render(<RecentEvents />)

    expect(await screen.findByText('No checkout events yet')).toBeVisible()
  })

  it('shows a retry action after an initial failure', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    getRecentEventsMock
      .mockRejectedValueOnce(new TypeError('private network detail'))
      .mockResolvedValueOnce(response)

    render(<RecentEvents />)

    expect(
      await screen.findByText('Unable to load checkout events.'),
    ).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Retry events' }))
    expect(await screen.findByText('Bottle')).toBeVisible()
    expect(screen.queryByText('private network detail')).not.toBeInTheDocument()
  })

  it('keeps events visible when a background refresh fails', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    vi.useFakeTimers()
    getRecentEventsMock
      .mockResolvedValueOnce(response)
      .mockRejectedValueOnce(new TypeError('offline'))

    render(<RecentEvents />)
    await act(async () => {
      await Promise.resolve()
    })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(EVENTS_POLL_INTERVAL_MS)
    })

    expect(screen.getByText('Bottle')).toBeVisible()
    expect(screen.getByText('Unable to refresh checkout events.')).toBeVisible()
  })
})
