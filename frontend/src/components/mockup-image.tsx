type MockupImageProps = {
  alt: string
  className?: string
  height?: number | string
  label?: string
  objectPosition?: string
  src?: string
  width?: number | string
}

export function MockupImage({
  alt,
  className = '',
  height = 200,
  label,
  objectPosition = 'center',
  src,
  width = '100%',
}: MockupImageProps) {
  return (
    <div
      className={`mockup-image ${className}`.trim()}
      style={{ width, height }}
    >
      {src ? (
        <img
          alt={alt}
          className="mockup-image__media"
          src={src}
          style={{ objectPosition }}
        />
      ) : (
        <div className="mockup-image__placeholder">
          <span>시뮬레이션 장면 준비 중</span>
        </div>
      )}
      {label ? <span className="mockup-image__label">{label}</span> : null}
    </div>
  )
}
