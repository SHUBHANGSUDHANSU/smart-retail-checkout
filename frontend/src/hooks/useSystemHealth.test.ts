import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { getHealth, getReadiness } from '../services/api'
import type { HealthResponse, ReadinessResponse } from '../types/api'
import {
  HEALTH_POLL_INTERVAL_MS,
  useSystemHealth,
} from './useSystemHealth'

vi.mock('../services/api', () => ({
  getHealth: vi.fn(),
  getReadiness: vi.fn(),
}))

const health: HealthResponse = { status: 'ok', uptime_seconds: 125 }
const readiness: ReadinessResponse = {
  status: 'ready',
  application_state: 'running',
  components: {
    core_services: 'ready',
    model: 'ready',
    camera: 'ready',
    vision_pipeline: 'ready',
    database: 'ready',
  },
}

const getHealthMock = vi.mocked(getHealth)
const getReadinessMock = vi.mocked(getReadiness)

beforeEach(() => {
  getHealthMock.mockReset()
  getReadinessMock.mockReset()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useSystemHealth', () => {
  it('loads liveness and readiness concurrently on mount', async () => {
    getHealthMock.mockResolvedValue(health)
    getReadinessMock.mockResolvedValue(readiness)

    const { result } = renderHook(() => useSystemHealth())

    expect(result.current.isInitialLoading).toBe(true)
    await waitFor(() => expect(result.current.health).toEqual(health))
    expect(result.current.readiness).toEqual(readiness)
    expect(result.current.healthError).toBeNull()
    expect(result.current.readinessError).toBeNull()
  })

  it('exposes a structured not-ready state as operational data', async () => {
    const notReady: ReadinessResponse = {
      ...readiness,
      status: 'not_ready',
      components: { ...readiness.components, camera: 'unavailable' },
    }
    getHealthMock.mockResolvedValue(health)
    getReadinessMock.mockResolvedValue(notReady)

    const { result } = renderHook(() => useSystemHealth())

    await waitFor(() => expect(result.current.readiness).toEqual(notReady))
    expect(result.current.readinessError).toBeNull()
  })

  it('retains prior status when a background refresh fails', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    vi.useFakeTimers()
    getHealthMock
      .mockResolvedValueOnce(health)
      .mockRejectedValueOnce(new TypeError('offline'))
    getReadinessMock
      .mockResolvedValueOnce(readiness)
      .mockRejectedValueOnce(new TypeError('offline'))

    const { result } = renderHook(() => useSystemHealth())
    await act(async () => Promise.resolve())
    await act(async () => {
      await vi.advanceTimersByTimeAsync(HEALTH_POLL_INTERVAL_MS)
    })

    expect(result.current.health).toEqual(health)
    expect(result.current.readiness).toEqual(readiness)
    expect(result.current.healthError).toBe('Backend unavailable.')
    expect(result.current.readinessError).toBe('Readiness unavailable.')
  })

  it('does not overlap health polling cycles', async () => {
    vi.useFakeTimers()
    let resolveHealth: ((value: HealthResponse) => void) | undefined
    let resolveReadiness: ((value: ReadinessResponse) => void) | undefined
    getHealthMock.mockImplementationOnce(
      () =>
        new Promise<HealthResponse>((resolve) => {
          resolveHealth = resolve
        }),
    )
    getReadinessMock.mockImplementationOnce(
      () =>
        new Promise<ReadinessResponse>((resolve) => {
          resolveReadiness = resolve
        }),
    )

    renderHook(() => useSystemHealth())
    await act(async () => {
      await vi.advanceTimersByTimeAsync(HEALTH_POLL_INTERVAL_MS * 2)
    })
    expect(getHealthMock).toHaveBeenCalledTimes(1)
    expect(getReadinessMock).toHaveBeenCalledTimes(1)

    await act(async () => {
      resolveHealth?.(health)
      resolveReadiness?.(readiness)
      await Promise.resolve()
    })
  })

  it('aborts both health requests when unmounted', async () => {
    const signals: AbortSignal[] = []
    const pending = (signal?: AbortSignal) => {
      if (signal) signals.push(signal)
      return new Promise<never>((_resolve, reject) => {
        signal?.addEventListener('abort', () => {
          reject(new DOMException('Request aborted.', 'AbortError'))
        })
      })
    }
    getHealthMock.mockImplementation(pending)
    getReadinessMock.mockImplementation(pending)

    const view = renderHook(() => useSystemHealth())
    view.unmount()

    expect(signals).toHaveLength(2)
    expect(signals.every((signal) => signal.aborted)).toBe(true)
    await act(async () => Promise.resolve())
  })
})
