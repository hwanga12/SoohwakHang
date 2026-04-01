/*
 * 이 컴포넌트는 프론트엔드 화면에서 섹션 공통 카드 역할을 맡는다.
 */
import type { PropsWithChildren, ReactNode } from 'react'

type SectionCardProps = PropsWithChildren<{
  title: string
  description: string
  eyebrow?: string
  action?: ReactNode
  className?: string
}>

/**
 * 섹션 카드 화면 조각을 렌더링하는 컴포넌트다.
 */
export function SectionCard({
  title,
  description,
  eyebrow,
  action,
  className,
  children,
}: SectionCardProps) {
  const classes = ['section-card', className].filter(Boolean).join(' ')

  return (
    <section className={classes}>
      <div className="section-head">
        <div>
          {eyebrow ? <span className="section-eyebrow">{eyebrow}</span> : null}
          <h3 className="section-title">{title}</h3>
          <p className="section-description">{description}</p>
        </div>
        {action}
      </div>
      {children}
    </section>
  )
}
