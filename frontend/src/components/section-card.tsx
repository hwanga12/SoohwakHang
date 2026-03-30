import type { PropsWithChildren, ReactNode } from 'react'

type SectionCardProps = PropsWithChildren<{
  title: string
  description: string
  eyebrow?: string
  action?: ReactNode
  className?: string
}>

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
