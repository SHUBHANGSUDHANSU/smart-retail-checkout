import { describe, expect, it } from 'vitest'

import { formatCompactTime, formatDateTime } from './dateTime'

describe('date and time formatting', () => {
  it('formats a persisted UTC timestamp as a readable full date', () => {
    expect(formatDateTime('2026-08-25T22:14:03Z', 'UTC')).toBe(
      '25 Aug 2026, 10:14 PM',
    )
  })

  it('formats a persisted timestamp for a compact event row', () => {
    expect(formatCompactTime('2026-08-25T22:14:03Z', 'UTC')).toBe(
      '10:14:03 PM',
    )
  })
})
