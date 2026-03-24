type AppIconProps = {
  name: string
  className?: string
  filled?: boolean
}

export function AppIcon({
  name,
  className,
  filled = false,
}: AppIconProps) {
  const classes = ['material-symbols-outlined', filled ? 'is-filled' : '', className]
    .filter(Boolean)
    .join(' ')

  return (
    <span aria-hidden="true" className={classes}>
      {name}
    </span>
  )
}
