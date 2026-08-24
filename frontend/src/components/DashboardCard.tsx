import type { ReactNode } from 'react'

interface DashboardCardProps {
  title: string
  eyebrow?: string
  children: ReactNode
}

export function DashboardCard({
  title,
  eyebrow,
  children,
}: DashboardCardProps) {
  return (
    <section className="dashboard-card">
      <div className="dashboard-card__heading">
        {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
        <h2>{title}</h2>
      </div>
      <div className="dashboard-card__content">{children}</div>
    </section>
  )
}
