import type { CartEventType, CheckoutEvent } from '../../types/history'
import { formatInr } from '../../utils/currency'
import { formatCompactTime, formatDateTime } from '../../utils/dateTime'
import { formatProductId } from '../../utils/productName'

interface EventListProps {
  events: CheckoutEvent[]
  timestampStyle?: 'compact' | 'full'
  timeZone?: string
}

const eventPresentation: Record<
  CartEventType,
  { action: string; badge: string; tone: string }
> = {
  ADD: { action: 'Added to cart', badge: 'Added', tone: 'positive' },
  REMOVE: { action: 'Removed from cart', badge: 'Removed', tone: 'warning' },
  RESET: { action: 'Active cart cleared', badge: 'Reset', tone: 'system' },
}

export function EventList({
  events,
  timestampStyle = 'compact',
  timeZone,
}: EventListProps) {
  return (
    <ul className="event-list" aria-label="Checkout events">
      {events.map((event) => {
        const presentation = eventPresentation[event.event_type]
        const title =
          event.event_type === 'RESET'
            ? 'Cart reset'
            : formatProductId(event.product_id ?? '')
        const formattedTimestamp =
          timestampStyle === 'full'
            ? formatDateTime(event.timestamp, timeZone)
            : formatCompactTime(event.timestamp, timeZone)

        return (
          <li
            className={`event-row event-row--${presentation.tone}`}
            key={event.id}
          >
            <span className="event-row__badge">{presentation.badge}</span>
            <div className="event-row__content">
              <strong>{title}</strong>
              <span>{presentation.action}</span>
              {event.unit_price !== null ? (
                <span>{formatInr(event.unit_price)}</span>
              ) : null}
            </div>
            <time dateTime={event.timestamp}>{formattedTimestamp}</time>
          </li>
        )
      })}
    </ul>
  )
}
