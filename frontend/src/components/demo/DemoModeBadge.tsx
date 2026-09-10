import { useDemoMode } from '../../demo/DemoModeContext'

export function DemoModeBadge() {
  const { manifest } = useDemoMode()
  if (manifest === null) return null

  return (
    <span className="demo-mode-badge" aria-label="Demo mode enabled">
      DEMO MODE
    </span>
  )
}
