import { useEffect, useRef, useState } from 'react'

import { useCart } from '../../hooks/useCart'
import type { CartResponse } from '../../types/cart'
import { formatInr } from '../../utils/currency'
import { DashboardCard } from '../DashboardCard'
import { CartItemRow } from './CartItemRow'
import { ResetCartConfirmation } from './ResetCartConfirmation'

export function CurrentCart() {
  const {
    cart,
    isInitialLoading,
    isResetting,
    loadError,
    resetError,
    refresh,
    reset,
    clearResetError,
  } = useCart()
  const [isConfirmingReset, setIsConfirmingReset] = useState(false)
  const [confirmationVersion, setConfirmationVersion] = useState<string | null>(
    null,
  )
  const [statusMessage, setStatusMessage] = useState<string | null>(null)
  const resetButtonRef = useRef<HTMLButtonElement>(null)
  const successStatusRef = useRef<HTMLParagraphElement>(null)

  const cartVersion = getCartVersion(cart)
  const isConfirmationCurrent =
    isConfirmingReset && confirmationVersion === cartVersion

  useEffect(() => {
    if (statusMessage !== null) {
      successStatusRef.current?.focus()
    }
  }, [statusMessage])

  const openReset = () => {
    clearResetError()
    setStatusMessage(null)
    setConfirmationVersion(cartVersion)
    setIsConfirmingReset(true)
  }

  const cancelReset = () => {
    clearResetError()
    setIsConfirmingReset(false)
    setConfirmationVersion(null)
    queueMicrotask(() => resetButtonRef.current?.focus())
  }

  const confirmReset = async () => {
    const succeeded = await reset()
    if (succeeded) {
      setIsConfirmingReset(false)
      setConfirmationVersion(null)
      setStatusMessage('Cart reset successfully.')
    }
  }

  const hasItems = (cart?.items.length ?? 0) > 0

  return (
    <DashboardCard title="Current Cart">
      <div className="current-cart">
        {isInitialLoading && cart === null ? (
          <p className="cart-state" role="status">
            Loading cart...
          </p>
        ) : null}

        {!isInitialLoading && cart === null && loadError ? (
          <div className="cart-notice" role="alert">
            <p>{loadError}</p>
            <button
              className="button button--secondary"
              type="button"
              onClick={() => void refresh()}
            >
              Retry
            </button>
          </div>
        ) : null}

        {cart !== null ? (
          <>
            {loadError ? (
              <div className="cart-notice cart-notice--inline" role="alert">
                <p>{loadError}</p>
                <button
                  className="button button--secondary"
                  type="button"
                  onClick={() => void refresh()}
                >
                  Retry
                </button>
              </div>
            ) : null}

            {hasItems ? (
              <>
                <ul className="cart-item-list" aria-label="Cart items">
                  {cart.items.map((item) => (
                    <CartItemRow key={item.product_id} item={item} />
                  ))}
                </ul>
                <div className="cart-total">
                  <span>
                    Total <small>({cart.total_quantity} items)</small>
                  </span>
                  <strong aria-label={`Cart total ${formatInr(cart.total)}`}>
                    {formatInr(cart.total)}
                  </strong>
                </div>
              </>
            ) : (
              <div className="cart-empty">
                <strong>Cart is empty</strong>
                <p>Move a detected product into the checkout zone to add it.</p>
              </div>
            )}

            <div className="cart-actions">
              <button
                ref={resetButtonRef}
                className="button button--danger-outline"
                type="button"
                onClick={openReset}
                disabled={!hasItems || isResetting || isConfirmationCurrent}
              >
                Reset Cart
              </button>
            </div>

            {isConfirmationCurrent ? (
              <ResetCartConfirmation
                canReset={hasItems}
                error={resetError}
                isResetting={isResetting}
                onCancel={cancelReset}
                onConfirm={() => void confirmReset()}
              />
            ) : null}

            {statusMessage ? (
              <p
                ref={successStatusRef}
                className="cart-success"
                role="status"
                aria-label={statusMessage}
                tabIndex={-1}
              >
                {statusMessage}
              </p>
            ) : null}
          </>
        ) : null}
      </div>
    </DashboardCard>
  )
}

function getCartVersion(cart: CartResponse | null): string | null {
  if (cart === null) {
    return null
  }

  return JSON.stringify({
    items: cart.items.map(({ product_id, quantity, unit_price, subtotal }) => ({
      product_id,
      quantity,
      unit_price,
      subtotal,
    })),
    total_quantity: cart.total_quantity,
    total: cart.total,
  })
}
