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
        <CurrentCart />
        <DashboardCard title="System Status">
          <SystemStatusSummary state={systemHealth} />
        </DashboardCard>
        <RecentEvents />
        <LiveMetrics />
      </div>
    </div>
  )
}
