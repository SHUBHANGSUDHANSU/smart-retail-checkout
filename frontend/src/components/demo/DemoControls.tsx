import { useEffect, useRef, useState } from 'react'

import { useDemoMode } from '../../demo/DemoModeContext'
import { addDemoItem, removeDemoItem } from '../../services/api'
import { formatInr } from '../../utils/currency'
import { DashboardCard } from '../DashboardCard'

type DemoAction = 'add' | 'remove'

interface PendingCommand {
  action: DemoAction
  productId: string
}

export function DemoControls() {
  const { manifest } = useDemoMode()
  const [pending, setPending] = useState<PendingCommand | null>(null)
  const [statusMessage, setStatusMessage] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const controllerRef = useRef<AbortController | null>(null)
  const commandInFlightRef = useRef(false)

  useEffect(() => () => controllerRef.current?.abort(), [])

  if (manifest === null) return null

  const runCommand = async (
    action: DemoAction,
    productId: string,
    productName: string,
  ) => {
    // The ref closes the small gap before React commits the disabled state.
    if (commandInFlightRef.current) return
    commandInFlightRef.current = true
    const controller = new AbortController()
    controllerRef.current = controller
    setPending({ action, productId })
    setStatusMessage(null)
    setErrorMessage(null)
    try {
      if (action === 'add') {
        await addDemoItem(productId, controller.signal)
      } else {
        await removeDemoItem(productId, controller.signal)
      }
      if (!controller.signal.aborted) {
        setStatusMessage(
          `${productName} ${action === 'add' ? 'added' : 'removed'}.`,
        )
      }
    } catch (error: unknown) {
      if (!controller.signal.aborted) {
        console.warn('Demo cart command failed.', error)
        setErrorMessage('Unable to update the demo cart.')
      }
    } finally {
      commandInFlightRef.current = false
      if (!controller.signal.aborted) setPending(null)
      if (controllerRef.current === controller) controllerRef.current = null
    }
  }

  return (
    <DashboardCard title="Demo controls" eyebrow="Safe simulation">
      <div className="demo-controls">
        <div className="demo-mode-copy">
          <strong>Computer vision is intentionally disabled.</strong>
          <p>{manifest.message}</p>
        </div>
        <ul className="demo-product-list" aria-label="Demo products">
          {manifest.products.map((product) => {
            const isCurrent = pending?.productId === product.product_id
            return (
              <li key={product.product_id} className="demo-product-row">
                <span>
                  <strong>{product.product_name}</strong>
                  <small>{formatInr(product.unit_price)}</small>
                </span>
                <span className="demo-product-actions">
                  <button
                    className="button button--secondary"
                    type="button"
                    disabled={pending !== null}
                    onClick={() =>
                      void runCommand(
                        'remove',
                        product.product_id,
                        product.product_name,
                      )
                    }
                  >
                    {isCurrent && pending.action === 'remove'
                      ? 'Removing…'
                      : `Remove ${product.product_name}`}
                  </button>
                  <button
                    className="button button--primary"
                    type="button"
                    disabled={pending !== null}
                    onClick={() =>
                      void runCommand(
                        'add',
                        product.product_id,
                        product.product_name,
                      )
                    }
                  >
                    {isCurrent && pending.action === 'add'
                      ? 'Adding…'
                      : `Add ${product.product_name}`}
                  </button>
                </span>
              </li>
            )
          })}
        </ul>
        {statusMessage ? <p role="status">{statusMessage}</p> : null}
        {errorMessage ? <p role="alert">{errorMessage}</p> : null}
      </div>
    </DashboardCard>
  )
}
