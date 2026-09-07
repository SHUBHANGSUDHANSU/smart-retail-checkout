import { DashboardCard } from '../components/DashboardCard'
import { CurrentCart } from '../components/cart/CurrentCart'
import { RecentEvents } from '../components/events/RecentEvents'
import { LiveMetrics } from '../components/observability/LiveMetrics'
import { SystemStatusSummary } from '../components/observability/SystemStatusSummary'
import { useSystemHealth } from '../hooks/useSystemHealth'

export function DashboardPage() {
  const systemHealth = useSystemHealth()

  return (
    <div className="page-stack">
      <header className="page-heading">
        <p className="eyebrow">Operations overview</p>
        <h1>Smart Retail Checkout</h1>
        <p>Realtime cashierless checkout monitoring dashboard</p>
      </header>
      <div className="dashboard-grid">
        <div className="dashboard-grid__status">
          <DashboardCard title="System Status" eyebrow="Operations">
            <SystemStatusSummary state={systemHealth} />
          </DashboardCard>
        </div>
        <div className="dashboard-grid__cart">
          <CurrentCart />
        </div>
        <div className="dashboard-grid__events">
          <RecentEvents />
        </div>
        <div className="dashboard-grid__metrics">
          <LiveMetrics />
        </div>
      </div>
    </div>
  )
}
