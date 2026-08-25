import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'

afterEach(() => vi.unstubAllGlobals())

function renderRoute(route: string) {
  vi.stubGlobal(
    'fetch',
    vi.fn<typeof fetch>(() => new Promise<Response>(() => undefined)),
  )

  return render(
    <MemoryRouter initialEntries={[route]}>
      <App />
    </MemoryRouter>,
  )
}

describe('application routing', () => {
  it.each([
    ['/', 'Smart Retail Checkout'],
    ['/sessions', 'Checkout Sessions'],
    ['/system', 'System'],
  ])('renders %s', (route, heading) => {
    renderRoute(route)

    expect(
      screen.getByRole('heading', { level: 1, name: heading }),
    ).toBeInTheDocument()
  })

  it('renders a useful Not Found page', () => {
    renderRoute('/missing')

    expect(
      screen.getByRole('heading', { name: 'Page not found' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: 'Return to Dashboard' }),
    ).toHaveAttribute('href', '/')
  })

  it('marks the active navigation link', () => {
    renderRoute('/sessions')

    expect(screen.getByRole('link', { name: 'Sessions' })).toHaveAttribute(
      'aria-current',
      'page',
    )
  })
})
