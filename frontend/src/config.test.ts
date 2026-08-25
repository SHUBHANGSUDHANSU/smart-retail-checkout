import { describe, expect, it } from 'vitest'

import { resolveApiBaseUrl } from './config'

describe('resolveApiBaseUrl', () => {
  it('uses the documented local development default', () => {
    expect(resolveApiBaseUrl(undefined)).toBe('http://localhost:8000')
  })

  it('normalizes whitespace and a trailing slash', () => {
    expect(resolveApiBaseUrl(' https://api.example.test/ ')).toBe(
      'https://api.example.test',
    )
  })

  it.each([
    'not-a-url',
    'ftp://localhost:8000',
    'http://user:secret@localhost:8000',
    'http://localhost:8000/api',
    'http://localhost:8000?debug=true',
  ])('rejects an unsafe API base URL: %s', (value) => {
    expect(() => resolveApiBaseUrl(value)).toThrow('VITE_API_BASE_URL')
  })
})
