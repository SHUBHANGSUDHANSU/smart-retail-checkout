import { useEffect, useState } from 'react'

import { getHealth } from '../services/api'
import type { HealthResponse } from '../types/api'

export type BackendHealthState =
  | { status: 'loading' }
  | { status: 'connected'; health: HealthResponse }
  | { status: 'unavailable' }

export function useBackendHealth(): BackendHealthState {
  const [state, setState] = useState<BackendHealthState>({ status: 'loading' })

  useEffect(() => {
    const controller = new AbortController()

    void getHealth(controller.signal)
      .then((health) => {
        if (!controller.signal.aborted) {
          setState({ status: 'connected', health })
        }
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return
        }

        console.warn('Backend health request failed.', error)
        setState({ status: 'unavailable' })
      })

    return () => controller.abort()
  }, [])

  return state
}
