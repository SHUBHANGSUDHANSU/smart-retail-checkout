import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { getMetrics } from '../services/api'
import type { MetricsResponse } from '../types/api'
import { METRICS_POLL_INTERVAL_MS, useMetrics } from './useMetrics'

vi.mock('../services/api', () => ({ getMetrics: vi.fn() }))

const metrics: MetricsResponse = {
  frames_processed_total: 8421,
  dropped_frames_total: 2,
  detections_total: 4391,
  active_tracks: 3,
  inference_latency_ms: 31.4,
  frame_processing_latency_ms: 38.8,
  current_fps: 28.2,
  checkout_enter_events_total: 7,
  checkout_exit_events_total: 2,
  cart_additions_total: 7,
  cart_removals_total: 2,
  cart_resets_total: 1,
  current_cart_items: 5,
  current_cart_total: 250,
  uptime_seconds: 8040,
  camera_errors_total: 1,
  persistence_errors_total: 0,
}

const getMetricsMock = vi.mocked(getMetrics)

beforeEach(() => {
  getMetricsMock.mockReset()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useMetrics', () => {
  it('fetches a metrics snapshot immediately', async () => {
    getMetricsMock.mockResolvedValue(metrics)

    const { result } = renderHook(() => useMetrics())

    expect(result.current.isInitialLoading).toBe(true)
    await waitFor(() => expect(result.current.metrics).toEqual(metrics))
    expect(result.current.error).toBeNull()
  })

  it('retains the previous snapshot after a background failure', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    vi.useFakeTimers()
    getMetricsMock
      .mockResolvedValueOnce(metrics)
      .mockRejectedValueOnce(new TypeError('backend stopped'))

    const { result } = renderHook(() => useMetrics())
    await act(async () => Promise.resolve())

    await act(async () => {
      await vi.advanceTimersByTimeAsync(METRICS_POLL_INTERVAL_MS)
    })

    expect(result.current.metrics).toEqual(metrics)
    expect(result.current.error).toBe('Unable to refresh metrics.')
  })

  it('waits for a request to settle before scheduling the next poll', async () => {
    vi.useFakeTimers()
    let resolveFirst: ((value: MetricsResponse) => void) | undefined
    getMetricsMock
      .mockImplementationOnce(
        () =>
          new Promise<MetricsResponse>((resolve) => {
            resolveFirst = resolve
          }),
      )
      .mockResolvedValue(metrics)

    renderHook(() => useMetrics())
    await act(async () => {
      await vi.advanceTimersByTimeAsync(METRICS_POLL_INTERVAL_MS * 3)
    })
    expect(getMetricsMock).toHaveBeenCalledTimes(1)

    await act(async () => {
      resolveFirst?.(metrics)
      await Promise.resolve()
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(METRICS_POLL_INTERVAL_MS)
    })
    expect(getMetricsMock).toHaveBeenCalledTimes(2)
  })

  it('aborts an active request when unmounted', async () => {
    let signal: AbortSignal | undefined
    getMetricsMock.mockImplementation((requestSignal) => {
      signal = requestSignal
      return new Promise<MetricsResponse>((_resolve, reject) => {
        requestSignal?.addEventListener('abort', () => {
          reject(new DOMException('Request aborted.', 'AbortError'))
        })
      })
    })

    const view = renderHook(() => useMetrics())
    view.unmount()

    expect(signal?.aborted).toBe(true)
    await act(async () => Promise.resolve())
  })
})
