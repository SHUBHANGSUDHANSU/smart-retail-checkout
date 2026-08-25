import { useRef, useState } from 'react'

import { useCart } from '../../hooks/useCart'
import { formatInr } from '../../utils/currency'
import { DashboardCard } from '../DashboardCard'
import { CartItemRow } from './CartItemRow'
import { ResetCartConfirmation } from './ResetCartConfirmation'

export function CurrentCart() {
  const { cart, isInitialLoading, isResetting, error, refresh, reset } =
    useCart()
  const [isConfirmingReset, setIsConfirmingReset] = useState(false)
  const resetButtonRef = useRef<HTMLButtonElement>(null)
  const cartStatusRef = useRef<HTMLDivElement>(null)

  const cancelReset = () => {
    setIsConfirmingReset(false)
    queueMicrotask(() => resetButtonRef.current?.focus())
  }

  const confirmReset = async () => {
    const succeeded = await reset()
    if (succeeded) {
      setIsConfirmingReset(false)
      queueMicrotask(() => cartStatusRef.current?.focus())
    }
  }

  const hasItems = (cart?.items.length ?? 0) > 0

  return (
    <DashboardCard title="Current Cart">
      <div className="current-cart" ref={cartStatusRef} tabIndex={-1}>
        {isInitialLoading && cart === null ? (
          <p className="cart-state" role="status">
            Loading cart...
          </p>
        ) : null}

        {!isInitialLoading && cart === null && error ? (
          <div className="cart-notice" role="alert">
            <p>{error}</p>
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
            {error ? (
              <div className="cart-notice cart-notice--inline" role="alert">
                <p>{error}</p>
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
                  <strong aria-label="Cart total">{formatInr(cart.total)}</strong>
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
                onClick={() => setIsConfirmingReset(true)}
                disabled={!hasItems || isResetting || isConfirmingReset}
              >
                Reset Cart
              </button>
            </div>

            {isConfirmingReset ? (
              <ResetCartConfirmation
                isResetting={isResetting}
                onCancel={cancelReset}
                onConfirm={() => void confirmReset()}
              />
            ) : null}
          </>
        ) : null}
      </div>
    </DashboardCard>
  )
}
