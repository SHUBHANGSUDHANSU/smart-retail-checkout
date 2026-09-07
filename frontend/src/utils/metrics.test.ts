import { describe, expect, it } from 'vitest'

import {
  formatCounter,
  formatFps,
  formatLatency,
  formatUptime,
} from './metrics'

describe('metric formatters', () => {
  it('formats FPS and latency with stable units and precision', () => {
    expect(formatFps(28.24)).toBe('28.2')
    expect(formatLatency(31.44)).toBe('31.4 ms')
  })

  it('formats counters with readable digit grouping', () => {
    expect(formatCounter(12_450)).toBe('12,450')
  })

  it('formats uptime without displaying insignificant units', () => {
    expect(formatUptime(8_040)).toBe('2h 14m')
    expect(formatUptime(125)).toBe('2m 5s')
    expect(formatUptime(12)).toBe('12s')
  })

  it('uses an em dash for missing or invalid values', () => {
    expect(formatFps(null)).toBe('—')
    expect(formatLatency(undefined)).toBe('—')
    expect(formatCounter(Number.NaN)).toBe('—')
    expect(formatUptime(-1)).toBe('—')
  })
})
