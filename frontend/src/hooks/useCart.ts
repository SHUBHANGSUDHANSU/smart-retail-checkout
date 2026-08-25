import { useCallback, useEffect, useRef, useState } from 'react'

import { getCart, resetCart } from '../services/api'
import type { CartResponse } from '../types/cart'

export const CART_POLL_INTERVAL_MS = 1_500

export interface CartState {
  cart: CartResponse | null
  isInitialLoading: boolean
  isResetting: boolean
  error: string | null
  refresh: () => Promise<void>
  reset: () => Promise<boolean>
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

export function useCart(): CartState {
  const [cart, setCart] = useState<CartResponse | null>(null)
  const [isInitialLoading, setIsInitialLoading] = useState(true)
  const [isResetting, setIsResetting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const mountedRef = useRef(false)
  const readControllerRef = useRef<AbortController | null>(null)
  const resetControllerRef = useRef<AbortController | null>(null)
  const readRequestRef = useRef<Promise<void> | null>(null)
  const resetRequestRef = useRef<Promise<boolean> | null>(null)

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
    readControllerRef.current = controller

    const request = getCart(controller.signal)
      .then((nextCart) => {
        if (!controller.signal.aborted && mountedRef.current) {
          setCart(nextCart)
          setError(null)
        }
      })
      .catch((requestError: unknown) => {
        if (controller.signal.aborted || isAbortError(requestError)) {
          return
        }

        console.warn('Cart request failed.', requestError)
        if (mountedRef.current) {
          setError('Unable to load cart.')
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
        setError(null)
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
          setError('Unable to reset cart.')
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

  useEffect(() => {
    mountedRef.current = true
    let pollTimer: ReturnType<typeof setTimeout> | undefined

    const poll = () => {
      void refresh().finally(() => {
        if (mountedRef.current) {
          pollTimer = setTimeout(poll, CART_POLL_INTERVAL_MS)
        }
      })
    }

    poll()

    return () => {
      mountedRef.current = false
      if (pollTimer !== undefined) {
        clearTimeout(pollTimer)
      }
      readControllerRef.current?.abort()
      resetControllerRef.current?.abort()
    }
  }, [refresh])

  return { cart, isInitialLoading, isResetting, error, refresh, reset }
}
