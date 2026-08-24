import type { BackendHealthState } from '../hooks/useBackendHealth'

interface ConnectionStatusProps {
  state: BackendHealthState
}

export function ConnectionStatus({ state }: ConnectionStatusProps) {
  const content =
    state.status === 'loading'
      ? {
          label: 'Checking backend...',
          detail: 'Waiting for the local FastAPI service.',
        }
      : state.status === 'connected'
        ? {
            label: 'Backend Connected',
            detail: 'FastAPI is responding.',
          }
        : {
            label: 'Backend Unavailable',
            detail: 'Unable to connect to backend.',
          }

  return (
    <div
      className={`connection-status connection-status--${state.status}`}
      role="status"
      aria-live="polite"
    >
      <span className="connection-status__dot" aria-hidden="true" />
      <div>
        <strong>{content.label}</strong>
        <p>{content.detail}</p>
      </div>
    </div>
  )
}
