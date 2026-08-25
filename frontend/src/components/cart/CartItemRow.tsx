import type { CartItem } from '../../types/cart'
import { formatInr } from '../../utils/currency'

interface CartItemRowProps {
  item: CartItem
}

export function CartItemRow({ item }: CartItemRowProps) {
  const formattedSubtotal = formatInr(item.subtotal)

  return (
    <li className="cart-item-row">
      <div className="cart-item-row__product">
        <strong>{item.product_name}</strong>
        <span>
          {formatInr(item.unit_price)} × {item.quantity}
        </span>
      </div>
      <strong
        className="cart-item-row__subtotal"
        aria-label={`${item.product_name} subtotal ${formattedSubtotal}`}
      >
        {formattedSubtotal}
      </strong>
    </li>
  )
}
