import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { LoadingState } from './LoadingState'

describe('LoadingState', () => {
  it('announces the operation while keeping decorative placeholders hidden', () => {
    const { container } = render(
      <LoadingState label="Loading checkout sessions..." lines={3} />,
    )

    expect(screen.getByRole('status')).toHaveTextContent(
      'Loading checkout sessions...',
    )
    const placeholders = container.querySelector('[aria-hidden="true"]')
    expect(placeholders).not.toBeNull()
    expect(placeholders?.children).toHaveLength(3)
  })
})
