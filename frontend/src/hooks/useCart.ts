import { useCallback, useEffect, useRef, useState } from 'react'

import { getCart, resetCart } from '../services/api'
import type { CartResponse } from '../types/cart'
import { useRealtime } from '../realtime/RealtimeContext'

export const CART_FALLBACK_INTERVAL_MS = 5_000
export const CART_POLL_INTERVAL_MS = CART_FALLBACK_INTERVAL_MS

export interface CartState {
  cart: CartResponse | null
  isInitialLoading: boolean
  isResetting: boolean
  loadError: string | null
  resetError: string | null
  refresh: () => Promise<void>
  reset: () => Promise<boolean>
  clearResetError: () => void
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

export function useCart(): CartState {
  const {
    status: realtimeStatus,
    connectionRevision,
    subscribe: subscribeRealtime,
  } = useRealtime()
  const [cart, setCart] = useState<CartResponse | null>(null)
  const [isInitialLoading, setIsInitialLoading] = useState(true)
  const [isResetting, setIsResetting] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [resetError, setResetError] = useState<string | null>(null)
  const mountedRef = useRef(false)
  const readControllerRef = useRef<AbortController | null>(null)
  const resetControllerRef = useRef<AbortController | null>(null)
  const readRequestRef = useRef<Promise<void> | null>(null)
  const resetRequestRef = useRef<Promise<boolean> | null>(null)
  const realtimeRevisionRef = useRef(0)

  const loadCart = useCallback((duringReset = false): Promise<void> => {
    const existingRead = readRequestRef.current
    if (existingRead) {
      return existingRead
    }

    const existingReset = resetRequestRef.current
    if (existingReset && !duringReset) {
      return existingReset.then(() => undefined)
    }

    const controller = new AbortController()
    const startingRealtimeRevision = realtimeRevisionRef.current
    readControllerRef.current = controller

    const request = getCart(controller.signal)
      .then((nextCart) => {
        if (
          !controller.signal.aborted &&
          mountedRef.current &&
          startingRealtimeRevision === realtimeRevisionRef.current
        ) {
          setCart(nextCart)
          setLoadError(null)
        }
      })
      .catch((requestError: unknown) => {
        if (controller.signal.aborted || isAbortError(requestError)) {
          return
        }

        console.warn('Cart request failed.', requestError)
        if (mountedRef.current) {
          setLoadError('Unable to load cart.')
        }
      })
      .finally(() => {
        if (readControllerRef.current === controller) {
          readControllerRef.current = null
        }
        if (readRequestRef.current === request) {
          readRequestRef.current = null
        }
        if (mountedRef.current) {
          setIsInitialLoading(false)
        }
      })

    readRequestRef.current = request
    return request
  }, [])

  const refresh = useCallback(() => loadCart(), [loadCart])

  const reset = useCallback((): Promise<boolean> => {
    const existingReset = resetRequestRef.current
    if (existingReset) {
      return existingReset
    }

    const controller = new AbortController()
    resetControllerRef.current = controller

    const request = (async () => {
      if (mountedRef.current) {
        setIsResetting(true)
        setResetError(null)
      }

      readControllerRef.current?.abort()
      await readRequestRef.current

      try {
        const response = await resetCart(controller.signal)
        if (controller.signal.aborted || !mountedRef.current) {
          return false
        }

        setCart(response.cart)
        await loadCart(true)
        return true
      } catch (requestError: unknown) {
        if (controller.signal.aborted || isAbortError(requestError)) {
          return false
        }

        console.warn('Cart reset failed.', requestError)
        if (mountedRef.current) {
          setResetError('Unable to reset cart.')
        }
        return false
      } finally {
        if (resetControllerRef.current === controller) {
          resetControllerRef.current = null
          resetRequestRef.current = null
        }
        if (mountedRef.current) {
          setIsResetting(false)
        }
      }
    })()

    resetRequestRef.current = request
    return request
  }, [loadCart])

  const clearResetError = useCallback(() => setResetError(null), [])

  useEffect(() => {
    mountedRef.current = true
    void refresh()

    return () => {
      mountedRef.current = false
      readControllerRef.current?.abort()
      resetControllerRef.current?.abort()
    }
  }, [refresh])

  useEffect(
    () =>
      subscribeRealtime((event) => {
        if (event.type === 'cart.updated' && mountedRef.current) {
          realtimeRevisionRef.current += 1
          setCart(event.payload)
          setLoadError(null)
          setIsInitialLoading(false)
        }
      }),
    [subscribeRealtime],
  )

  useEffect(() => {
    if (realtimeStatus === 'live') return
    let timer: ReturnType<typeof setTimeout>
    let cancelled = false
    const poll = () => {
      void refresh().finally(() => {
        if (mountedRef.current && !cancelled) {
          timer = setTimeout(poll, CART_FALLBACK_INTERVAL_MS)
        }
      })
    }
    timer = setTimeout(poll, CART_FALLBACK_INTERVAL_MS)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [realtimeStatus, refresh])

  useEffect(() => {
    if (connectionRevision > 0) void refresh()
  }, [connectionRevision, refresh])

  return {
    cart,
    isInitialLoading,
    isResetting,
    loadError,
    resetError,
    refresh,
    reset,
    clearResetError,
  }
}
