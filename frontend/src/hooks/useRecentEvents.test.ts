import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { getRecentEvents } from '../services/api'
import type { RecentEventsResponse } from '../types/history'
import { EVENTS_POLL_INTERVAL_MS, useRecentEvents } from './useRecentEvents'

vi.mock('../services/api', () => ({
  getRecentEvents: vi.fn(),
}))

const response: RecentEventsResponse = {
  events: [
    {
      id: 12,
      session_id: 4,
      timestamp: '2026-08-25T16:44:03Z',
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

describe('useRecentEvents', () => {
  it('fetches persisted events immediately', async () => {
    getRecentEventsMock.mockResolvedValue(response)

    const { result } = renderHook(() => useRecentEvents())

    expect(result.current.isInitialLoading).toBe(true)
    await waitFor(() => expect(result.current.events).toEqual(response.events))
    expect(result.current.error).toBeNull()
  })

  it('retains existing events when a background refresh fails', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    vi.useFakeTimers()
    getRecentEventsMock
      .mockResolvedValueOnce(response)
      .mockRejectedValueOnce(new TypeError('private network detail'))

    const { result } = renderHook(() => useRecentEvents())
    await act(async () => {
      await Promise.resolve()
    })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(EVENTS_POLL_INTERVAL_MS)
    })

    expect(result.current.events).toEqual(response.events)
    expect(result.current.error).toBe('Unable to load checkout events.')
  })

  it('does not overlap polling requests', async () => {
    vi.useFakeTimers()
    let resolveFirst: ((value: RecentEventsResponse) => void) | undefined
    getRecentEventsMock
      .mockImplementationOnce(
        () =>
          new Promise<RecentEventsResponse>((resolve) => {
            resolveFirst = resolve
          }),
      )
      .mockResolvedValue(response)

    renderHook(() => useRecentEvents())
    expect(getRecentEventsMock).toHaveBeenCalledTimes(1)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(EVENTS_POLL_INTERVAL_MS * 3)
    })
    expect(getRecentEventsMock).toHaveBeenCalledTimes(1)

    await act(async () => {
      resolveFirst?.(response)
      await Promise.resolve()
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(EVENTS_POLL_INTERVAL_MS)
    })
    expect(getRecentEventsMock).toHaveBeenCalledTimes(2)
  })

  it('aborts an active request when unmounted', async () => {
    let signal: AbortSignal | undefined
    getRecentEventsMock.mockImplementation((_limit, requestSignal) => {
      signal = requestSignal
      return new Promise<RecentEventsResponse>((_resolve, reject) => {
        requestSignal?.addEventListener('abort', () => {
          reject(new DOMException('Request aborted.', 'AbortError'))
        })
      })
    })

    const view = renderHook(() => useRecentEvents())
    view.unmount()

    expect(signal?.aborted).toBe(true)
    await act(async () => {
      await Promise.resolve()
    })
  })
})
