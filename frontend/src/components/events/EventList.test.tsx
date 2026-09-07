import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { CheckoutEvent } from '../../types/history'
import { EventList } from './EventList'

const events: CheckoutEvent[] = [
  {
    id: 3,
    session_id: 4,
    timestamp: '2026-08-25T22:14:24Z',
    track_id: null,
    product_id: null,
    event_type: 'RESET',
    unit_price: null,
  },
  {
    id: 2,
    session_id: 4,
    timestamp: '2026-08-25T22:14:08Z',
    track_id: 12,
    product_id: 'apple',
    event_type: 'REMOVE',
    unit_price: 45,
  },
  {
    id: 1,
    session_id: 4,
    timestamp: '2026-08-25T22:14:03Z',
    track_id: 7,
    product_id: 'water_bottle',
    event_type: 'ADD',
    unit_price: 40,
  },
]

describe('EventList', () => {
  it('maps persisted event types to understandable product activity', () => {
    render(<EventList events={events} timeZone="UTC" />)

    expect(screen.getByRole('list', { name: 'Checkout events' })).toBeVisible()
    expect(screen.getByText('Water Bottle')).toBeVisible()
    expect(screen.getByText('Added to cart')).toBeVisible()
    expect(screen.getByText('Apple')).toBeVisible()
    expect(screen.getByText('Removed from cart')).toBeVisible()
    expect(screen.getByText('Cart reset')).toBeVisible()
    expect(screen.getByText('Active cart cleared')).toBeVisible()
    expect(screen.getByText('10:14:03 PM')).toHaveAttribute(
      'datetime',
      '2026-08-25T22:14:03Z',
    )
  })
})
