const decimalFormatter = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
})

const counterFormatter = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 0,
})

function isUsableMetric(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0
}

export function formatFps(value: number | null | undefined): string {
  return isUsableMetric(value) ? decimalFormatter.format(value) : '—'
}

export function formatLatency(value: number | null | undefined): string {
  return isUsableMetric(value) ? `${decimalFormatter.format(value)} ms` : '—'
}

export function formatCounter(value: number | null | undefined): string {
  return isUsableMetric(value) ? counterFormatter.format(value) : '—'
}

export function formatUptime(value: number | null | undefined): string {
  if (!isUsableMetric(value)) {
    return '—'
  }

  const totalSeconds = Math.floor(value)
  const days = Math.floor(totalSeconds / 86_400)
  const hours = Math.floor((totalSeconds % 86_400) / 3_600)
  const minutes = Math.floor((totalSeconds % 3_600) / 60)
  const seconds = totalSeconds % 60

  if (days > 0) {
    return `${days}d ${hours}h`
  }
  if (hours > 0) {
    return `${hours}h ${minutes}m`
  }
  if (minutes > 0) {
    return `${minutes}m ${seconds}s`
  }
  return `${seconds}s`
}
