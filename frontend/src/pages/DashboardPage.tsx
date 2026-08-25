import { ConnectionStatus } from '../components/ConnectionStatus'
import { DashboardCard } from '../components/DashboardCard'
import { useBackendHealth } from '../hooks/useBackendHealth'

export function DashboardPage() {
  const backendHealth = useBackendHealth()

  return (
    <div className="page-stack">
      <header className="page-heading">
        <p className="eyebrow">Operations overview</p>
        <h1>Smart Retail Checkout</h1>
        <p>Realtime cashierless checkout monitoring dashboard</p>
      </header>
      <div className="dashboard-grid">
        <DashboardCard title="Current Cart">
          <p className="empty-copy">No data loaded yet</p>
        </DashboardCard>
        <DashboardCard title="System Status">
          <ConnectionStatus state={backendHealth} />
        </DashboardCard>
        <DashboardCard title="Recent Events">
          <p className="empty-copy">No data loaded yet</p>
        </DashboardCard>
        <DashboardCard title="Live Metrics">
          <p className="empty-copy">No data loaded yet</p>
        </DashboardCard>
      </div>
    </div>
  )
}
