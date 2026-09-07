import { useMetrics } from '../../hooks/useMetrics'
import { formatCounter, formatFps, formatLatency } from '../../utils/metrics'
import { DashboardCard } from '../DashboardCard'
import { MetricGrid } from './MetricGrid'

export function LiveMetrics() {
  const { metrics, isInitialLoading, error, refresh } = useMetrics()
  const items = metrics
    ? [
        { label: 'FPS', value: formatFps(metrics.current_fps) },
        {
          label: 'Inference latency',
          value: formatLatency(metrics.inference_latency_ms),
        },
        { label: 'Active tracks', value: formatCounter(metrics.active_tracks) },
        {
          label: 'Frames processed',
          value: formatCounter(metrics.frames_processed_total),
        },
        {
          label: 'Dropped frames',
          value: formatCounter(metrics.dropped_frames_total),
        },
      ]
    : null

  return (
    <DashboardCard title="Live Metrics">
      <div className="observability-content">
        {isInitialLoading && metrics === null ? (
          <p className="observability-state" role="status">
            Loading live metrics...
          </p>
        ) : null}

        {!isInitialLoading && metrics === null && error ? (
          <div className="observability-notice" role="alert">
            <p>Unable to load metrics.</p>
            <button
              className="button button--secondary"
              type="button"
              aria-label="Retry metrics"
              onClick={() => void refresh()}
            >
              Retry
            </button>
          </div>
        ) : null}

        {items ? (
          <>
            {error ? (
              <div
                className="observability-notice observability-notice--inline"
                role="alert"
              >
                <p>Unable to refresh metrics.</p>
                <button
                  className="button button--secondary"
                  type="button"
                  aria-label="Retry metrics"
                  onClick={() => void refresh()}
                >
                  Retry
                </button>
              </div>
            ) : null}
            <MetricGrid items={items} ariaLabel="Live operational metrics" />
          </>
        ) : null}
      </div>
    </DashboardCard>
  )
}
