import { useRealtime } from '../../realtime/RealtimeContext'

const labels = {
  connecting: 'Connecting',
  live: 'Live',
  reconnecting: 'Reconnecting',
  offline: 'Offline',
} as const

export function RealtimeStatus() {
  const { status } = useRealtime()
  return (
    <div
      className={`realtime-status realtime-status--${status}`}
      aria-live="polite"
      aria-label={`Realtime connection: ${labels[status]}`}
    >
      <span className="realtime-status__dot" aria-hidden="true" />
      <span>Realtime</span>
      <strong>{labels[status]}</strong>
    </div>
  )
}
