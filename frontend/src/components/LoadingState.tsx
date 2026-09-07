interface LoadingStateProps {
  label: string
  lines?: number
}

export function LoadingState({ label, lines = 2 }: LoadingStateProps) {
  return (
    <div className="loading-state" role="status">
      <span className="sr-only">{label}</span>
      <div className="loading-state__placeholders" aria-hidden="true">
        {Array.from({ length: lines }, (_, index) => (
          <span className="loading-state__line" key={index} />
        ))}
      </div>
    </div>
  )
}
