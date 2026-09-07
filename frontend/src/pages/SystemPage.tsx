import { DashboardCard } from '../components/DashboardCard'
import { MetricGrid, type MetricItem } from '../components/observability/MetricGrid'
import {
  StatusIndicator,
  type OperationalStatus,
} from '../components/observability/StatusIndicator'
import { useMetrics } from '../hooks/useMetrics'
import { useSystemHealth } from '../hooks/useSystemHealth'
import type { ReadinessComponentStatus } from '../types/api'
import { formatInr } from '../utils/currency'
import {
  formatCounter,
  formatFps,
  formatLatency,
  formatUptime,
} from '../utils/metrics'

export function SystemPage() {
  const healthState = useSystemHealth()
  const metricsState = useMetrics()

  return (
    <div className="page-stack">
      <header className="page-heading">
        <p className="eyebrow">Runtime overview</p>
        <h1>System Health</h1>
        <p>Live operational status from the local checkout runtime.</p>
      </header>

      <div className="system-overview-grid">
        <DashboardCard title="Liveness">
          <HealthOverview state={healthState} />
        </DashboardCard>
        <DashboardCard title="Readiness">
          <ReadinessOverview state={healthState} />
        </DashboardCard>
      </div>

      <DashboardCard title="Component Readiness">
        <ComponentReadiness state={healthState} />
      </DashboardCard>

      <DashboardCard title="Operational Metrics">
        <OperationalMetrics state={metricsState} />
      </DashboardCard>
    </div>
  )
}

type HealthState = ReturnType<typeof useSystemHealth>
type MetricsState = ReturnType<typeof useMetrics>

function HealthOverview({ state }: { state: HealthState }) {
  if (state.healthError && state.health === null) {
    return <StatusIndicator label="Liveness" status="unavailable" detail="Liveness unavailable." />
  }
  if (state.health) {
    return (
      <StatusIndicator
        label="Liveness"
        status={state.healthError ? 'unavailable' : 'healthy'}
        detail={`Application process is responding. Process uptime ${formatUptime(
          state.health.uptime_seconds,
        )}.`}
      />
    )
  }
  return <StatusIndicator label="Liveness" status="loading" detail="Checking liveness..." />
}

function ReadinessOverview({ state }: { state: HealthState }) {
  if (state.readinessError && state.readiness === null) {
    return (
      <div className="observability-content">
        <StatusIndicator label="Readiness" status="unavailable" detail="Readiness unavailable." />
        <RetryStatusButton refresh={state.refresh} />
      </div>
    )
  }
  if (state.readiness) {
    const ready = state.readiness.status === 'ready'
    return (
      <div className="observability-content">
        <StatusIndicator
          label="Readiness"
          status={state.readinessError ? 'unavailable' : ready ? 'ready' : 'degraded'}
          detail={
            ready
              ? 'Ready to process checkout work.'
              : 'Not ready for checkout work.'
          }
        />
        <p className="application-state">
          Application state: {formatComponentName(state.readiness.application_state)}
        </p>
      </div>
    )
  }
  return <StatusIndicator label="Readiness" status="loading" detail="Checking readiness..." />
}

function RetryStatusButton({ refresh }: { refresh: () => Promise<void> }) {
  return (
    <button
      className="button button--secondary"
      type="button"
      aria-label="Retry system status"
      onClick={() => void refresh()}
    >
      Retry status
    </button>
  )
}

function ComponentReadiness({ state }: { state: HealthState }) {
  if (state.readiness === null) {
    return (
      <p className="observability-state">
        {state.isInitialLoading
          ? 'Loading component readiness...'
          : 'Component readiness unavailable.'}
      </p>
    )
  }

  const components = Object.entries(state.readiness.components)
  if (components.length === 0) {
    return <p className="observability-state">No component readiness data available.</p>
  }

  return (
    <div className="component-status-grid">
      {components.map(([name, status]) => (
        <StatusIndicator
          key={name}
          label={formatComponentName(name)}
          status={componentOperationalStatus(status)}
        />
      ))}
    </div>
  )
}

function OperationalMetrics({ state }: { state: MetricsState }) {
  if (state.isInitialLoading && state.metrics === null) {
    return <p className="observability-state">Loading operational metrics...</p>
  }
  if (state.metrics === null) {
    return (
      <div className="observability-notice" role="alert">
        <p>Unable to load metrics.</p>
        <button
          className="button button--secondary"
          type="button"
          aria-label="Retry metrics"
          onClick={() => void state.refresh()}
        >
          Retry
        </button>
      </div>
    )
  }

  const metrics = state.metrics
  const groups: { title: string; items: MetricItem[] }[] = [
    {
      title: 'Vision',
      items: [
        { label: 'FPS', value: formatFps(metrics.current_fps) },
        { label: 'Inference latency', value: formatLatency(metrics.inference_latency_ms) },
        { label: 'Frame processing', value: formatLatency(metrics.frame_processing_latency_ms) },
        { label: 'Active tracks', value: formatCounter(metrics.active_tracks) },
        { label: 'Frames processed', value: formatCounter(metrics.frames_processed_total) },
        { label: 'Detections', value: formatCounter(metrics.detections_total) },
        { label: 'Dropped frames', value: formatCounter(metrics.dropped_frames_total) },
      ],
    },
    {
      title: 'Checkout',
      items: [
        { label: 'Enter events', value: formatCounter(metrics.checkout_enter_events_total) },
        { label: 'Exit events', value: formatCounter(metrics.checkout_exit_events_total) },
        { label: 'Cart additions', value: formatCounter(metrics.cart_additions_total) },
        { label: 'Cart removals', value: formatCounter(metrics.cart_removals_total) },
        { label: 'Cart resets', value: formatCounter(metrics.cart_resets_total) },
        { label: 'Current cart items', value: formatCounter(metrics.current_cart_items) },
        { label: 'Current cart total', value: formatInr(metrics.current_cart_total) },
      ],
    },
    {
      title: 'Runtime',
      items: [
        { label: 'Uptime', value: formatUptime(metrics.uptime_seconds) },
        { label: 'Camera errors', value: formatCounter(metrics.camera_errors_total) },
        { label: 'Persistence errors', value: formatCounter(metrics.persistence_errors_total) },
      ],
    },
  ]

  return (
    <div className="metric-groups">
      {state.error ? (
        <div className="observability-notice observability-notice--inline" role="alert">
          <p>Unable to refresh metrics.</p>
          <button
            className="button button--secondary"
            type="button"
            aria-label="Retry metrics"
            onClick={() => void state.refresh()}
          >
            Retry
          </button>
        </div>
      ) : null}
      {groups.map((group) => (
        <section className="metric-group" key={group.title}>
          <h3>{group.title}</h3>
          <MetricGrid items={group.items} ariaLabel={`${group.title} metrics`} />
        </section>
      ))}
    </div>
  )
}

function componentOperationalStatus(
  status: ReadinessComponentStatus,
): OperationalStatus {
  if (status === 'ready') return 'ready'
  if (status === 'unavailable') return 'unavailable'
  if (status === 'initializing') return 'loading'
  return 'disabled'
}

function formatComponentName(name: string): string {
  return name
    .split('_')
    .filter(Boolean)
    .map((word) => `${word.charAt(0).toUpperCase()}${word.slice(1)}`)
    .join(' ')
}
