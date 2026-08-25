type DateTimeStyle = 'compact' | 'full'

function formatTimestamp(
  timestamp: string,
  style: DateTimeStyle,
  timeZone?: string,
): string {
  const date = new Date(timestamp)
  const options: Intl.DateTimeFormatOptions =
    style === 'full'
      ? {
          day: 'numeric',
          month: 'short',
          year: 'numeric',
          hour: 'numeric',
          minute: '2-digit',
          hour12: true,
          timeZone,
        }
      : {
          hour: 'numeric',
          minute: '2-digit',
          second: '2-digit',
          hour12: true,
          timeZone,
        }

  return new Intl.DateTimeFormat('en-IN', options)
    .format(date)
    .replace(/\b(am|pm)\b/gi, (period) => period.toUpperCase())
}

export function formatDateTime(timestamp: string, timeZone?: string): string {
  return formatTimestamp(timestamp, 'full', timeZone)
}

export function formatCompactTime(timestamp: string, timeZone?: string): string {
  return formatTimestamp(timestamp, 'compact', timeZone)
}
