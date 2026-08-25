import { describe, expect, it } from 'vitest'

import { formatProductId } from './productName'

describe('product identifier formatting', () => {
  it('turns a persisted detector product ID into a readable label', () => {
    expect(formatProductId('water_bottle')).toBe('Water Bottle')
    expect(formatProductId('coffee-cup')).toBe('Coffee Cup')
  })
})
