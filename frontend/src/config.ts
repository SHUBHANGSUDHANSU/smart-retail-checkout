const DEFAULT_API_BASE_URL = 'http://localhost:8000'

export function resolveApiBaseUrl(value: string | undefined): string {
  const candidate = value?.trim() || DEFAULT_API_BASE_URL
  let parsed: URL
  try {
    parsed = new URL(candidate)
  } catch {
    throw new Error('VITE_API_BASE_URL must be a valid absolute URL.')
  }

  if (!['http:', 'https:'].includes(parsed.protocol)) {
    throw new Error('VITE_API_BASE_URL must use HTTP or HTTPS.')
  }
  if (parsed.username || parsed.password) {
    throw new Error('VITE_API_BASE_URL cannot contain credentials.')
  }
  if (parsed.pathname !== '/' || parsed.search || parsed.hash) {
    throw new Error('VITE_API_BASE_URL must contain an origin without a path.')
  }

  return parsed.origin
}

export const appConfig = Object.freeze({
  apiBaseUrl: resolveApiBaseUrl(import.meta.env.VITE_API_BASE_URL),
})
