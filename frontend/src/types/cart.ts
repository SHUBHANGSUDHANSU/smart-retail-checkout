export interface CartItem {
  product_id: string
  product_name: string
  quantity: number
  unit_price: number
  subtotal: number
}

export interface CartResponse {
  items: CartItem[]
  total_quantity: number
  total: number
}

export interface CartResetResponse {
  status: string
  removed_track_count: number
  cart: CartResponse
}
