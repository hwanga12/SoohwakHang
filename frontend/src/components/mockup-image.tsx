type MockupImageProps = {
  width?: string | number;
  height?: string | number;
  label?: string;
  className?: string;
};

export function MockupImage({ width = '100%', height = 200, label = '[목업]', className = '' }: MockupImageProps) {
  return (
    <div 
      className={`mockup-image-container ${className}`} 
      style={{ 
        width, 
        height, 
        backgroundColor: '#e5e7eb', // Tailwind gray-200
        position: 'relative',
        borderRadius: '16px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        overflow: 'hidden',
        border: '1px dashed #9ca3af' // dashed border to indicate it's a placeholder
      }}
    >
      <span style={{
        position: 'absolute',
        top: '8px',
        left: '8px',
        backgroundColor: 'rgba(0,0,0,0.5)',
        color: 'white',
        fontSize: '0.75rem',
        padding: '2px 6px',
        borderRadius: '4px',
        fontWeight: 'bold'
      }}>
        {label}
      </span>
      <span style={{ color: '#6b7280', fontSize: '0.9rem' }}>이미지 영역</span>
    </div>
  );
}
