export interface MetricItem {
  label: string
  value: string
}

interface MetricGridProps {
  items: readonly MetricItem[]
  ariaLabel: string
}

export function MetricGrid({ items, ariaLabel }: MetricGridProps) {
  return (
    <dl className="metric-grid" aria-label={ariaLabel}>
      {items.map((item) => (
        <div className="metric-grid__item" key={item.label}>
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  )
}
