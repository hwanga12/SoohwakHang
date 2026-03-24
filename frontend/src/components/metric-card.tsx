type MetricCardTone = 'accent' | 'warning' | 'danger'

type MetricCardProps = {
  label: string
  value: string
  meta: string
  tone?: MetricCardTone
}

export function MetricCard({
  label,
  value,
  meta,
  tone = 'accent',
}: MetricCardProps) {
  return (
    <article className={`metric-card metric-card--${tone}`}>
      <span className="metric-label">{label}</span>
      <p className="metric-value">{value}</p>
      <p className="metric-meta">{meta}</p>
    </article>
  )
}
