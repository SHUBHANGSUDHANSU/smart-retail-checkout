import type { SystemHealthState } from '../../hooks/useSystemHealth'
import type { ReadinessComponentStatus } from '../../types/api'
import { StatusIndicator, type OperationalStatus } from './StatusIndicator'

function componentStatus(status: ReadinessComponentStatus): OperationalStatus {
  if (status === 'ready') return 'ready'
  if (status === 'unavailable') return 'unavailable'
  if (status === 'initializing') return 'loading'
  return 'disabled'
}

export function SystemStatusSummary({ state }: { state: SystemHealthState }) {
  const backendStatus: OperationalStatus = state.healthError
    ? 'unavailable'
    : state.health
      ? 'healthy'
      : state.isInitialLoading
        ? 'loading'
        : 'unknown'
  const systemStatus: OperationalStatus = state.readinessError
    ? 'unavailable'
    : state.readiness?.status === 'ready'
      ? 'ready'
      : state.readiness?.status === 'not_ready'
        ? 'degraded'
        : state.isInitialLoading
          ? 'loading'
          : 'unknown'

  const componentRows = ['camera', 'database'].flatMap((name) => {
    const status = state.readiness?.components[name]
    return status
      ? [
          <StatusIndicator
            key={name}
            label={name === 'camera' ? 'Camera' : 'Database'}
            status={componentStatus(status)}
          />,
        ]
      : []
  })

  return (
    <div className="status-list">
      <StatusIndicator label="Backend" status={backendStatus} />
      <StatusIndicator label="System" status={systemStatus} />
      {componentRows}
      {state.healthError || state.readinessError ? (
        <div className="observability-notice observability-notice--inline" role="alert">
          <p>Some status data could not be refreshed.</p>
          <button
            className="button button--secondary"
            type="button"
            aria-label="Retry system status"
            onClick={() => void state.refresh()}
          >
            Retry
          </button>
        </div>
      ) : null}
    </div>
  )
}
