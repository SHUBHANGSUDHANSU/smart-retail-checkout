export function formatProductId(productId: string): string {
  return productId
    .split(/[_-]+/)
    .filter(Boolean)
    .map((word) => `${word.charAt(0).toUpperCase()}${word.slice(1)}`)
    .join(' ')
}
