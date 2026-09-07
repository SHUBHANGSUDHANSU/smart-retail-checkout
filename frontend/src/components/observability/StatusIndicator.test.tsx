import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { StatusIndicator } from './StatusIndicator'

describe('StatusIndicator', () => {
  it('communicates status with text rather than color alone', () => {
    render(
      <StatusIndicator
        label="Camera"
        status="unavailable"
        detail="Camera initialization failed."
      />,
    )

    expect(screen.getByText('Camera')).toBeVisible()
    expect(screen.getByText('Unavailable')).toBeVisible()
    expect(screen.getByText('Camera initialization failed.')).toBeVisible()
  })
})
