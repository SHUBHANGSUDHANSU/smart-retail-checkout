import { createContext, useContext } from 'react'

import type { DemoManifest } from '../types/demo'

export interface DemoModeState {
  manifest: DemoManifest | null
  isLoading: boolean
  discoveryError: string | null
  refresh: () => Promise<void>
}

export const DemoModeContext = createContext<DemoModeState>({
  manifest: null,
  isLoading: false,
  discoveryError: null,
  refresh: async () => undefined,
})

export function useDemoMode(): DemoModeState {
  return useContext(DemoModeContext)
}
