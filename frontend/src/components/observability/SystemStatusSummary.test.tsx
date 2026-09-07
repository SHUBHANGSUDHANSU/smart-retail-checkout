import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { SystemHealthState } from '../../hooks/useSystemHealth'
import { SystemStatusSummary } from './SystemStatusSummary'

const refresh = vi.fn(async () => undefined)

function state(overrides: Partial<SystemHealthState> = {}): SystemHealthState {
  return {
    health: { status: 'ok', uptime_seconds: 125 },
    readiness: {
      status: 'ready',
      application_state: 'running',
      components: {
        core_services: 'ready',
        model: 'ready',
        camera: 'ready',
        vision_pipeline: 'ready',
        database: 'ready',
      },
    },
    isInitialLoading: false,
    healthError: null,
    readinessError: null,
    refresh,
    ...overrides,
  }
}

describe('SystemStatusSummary', () => {
  it('shows concise backend and critical-component status', () => {
    render(<SystemStatusSummary state={state()} />)

    expect(screen.getByText('Backend')).toBeVisible()
    expect(screen.getByText('Healthy')).toBeVisible()
    expect(screen.getByText('System')).toBeVisible()
    expect(screen.getAllByText('Ready').length).toBeGreaterThanOrEqual(3)
    expect(screen.getByText('Camera')).toBeVisible()
    expect(screen.getByText('Database')).toBeVisible()
  })

  it('labels not-ready and unavailable states without relying on color', () => {
    const degraded = state({
      readiness: {
        status: 'not_ready',
        application_state: 'running',
        components: { camera: 'unavailable', database: 'ready' },
      },
    })

    render(<SystemStatusSummary state={degraded} />)

    expect(screen.getByText('Degraded')).toBeVisible()
    expect(screen.getByText('Unavailable')).toBeVisible()
  })
})
