export type OperationalStatus =
  | 'healthy'
  | 'ready'
  | 'degraded'
  | 'unavailable'
  | 'loading'
  | 'unknown'
  | 'disabled'

interface StatusIndicatorProps {
  label: string
  status: OperationalStatus
  detail?: string
}

const statusLabels: Record<OperationalStatus, string> = {
  healthy: 'Healthy',
  ready: 'Ready',
  degraded: 'Degraded',
  unavailable: 'Unavailable',
  loading: 'Loading',
  unknown: 'Unknown',
  disabled: 'Disabled',
}

export function StatusIndicator({
  label,
  status,
  detail,
}: StatusIndicatorProps) {
  return (
    <div className={`status-indicator status-indicator--${status}`}>
      <span className="status-indicator__dot" aria-hidden="true" />
      <div className="status-indicator__body">
        <span className="status-indicator__label">{label}</span>
        {detail ? <span className="status-indicator__detail">{detail}</span> : null}
      </div>
      <strong className="status-indicator__value">{statusLabels[status]}</strong>
    </div>
  )
}
