import { describe, expect, it } from 'vitest'

import { formatInr } from './currency'

describe('formatInr', () => {
  it.each([
    [0, '₹0'],
    [40, '₹40'],
    [1250, '₹1,250'],
  ])('formats integer rupees %i as %s', (amount, expected) => {
    expect(formatInr(amount)).toBe(expected)
  })
})
