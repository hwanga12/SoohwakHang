/*
 * 이 컴포넌트는 프론트엔드 화면에서 핵심 수치를 보여주는 카드 역할을 맡는다.
 */
type MetricCardTone = 'accent' | 'warning' | 'danger'

type MetricCardProps = {
  label: string
  value: string
  meta: string
  tone?: MetricCardTone
}

/**
 * 지표 카드 화면 조각을 렌더링하는 컴포넌트다.
 */
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
