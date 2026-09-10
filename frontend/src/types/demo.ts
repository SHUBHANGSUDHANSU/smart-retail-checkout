import type { CartResponse } from './cart'

export interface DemoProduct {
  product_id: string
  product_name: string
  unit_price: number
}

export interface DemoManifest {
  mode: 'demo'
  vision_active: false
  message: string
  products: DemoProduct[]
}

export interface DemoMutationResponse {
  status: 'added' | 'removed'
  track_id: number
  product: DemoProduct
  cart: CartResponse
}
