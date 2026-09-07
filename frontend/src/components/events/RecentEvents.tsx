import { useRecentEvents } from '../../hooks/useRecentEvents'
import { DashboardCard } from '../DashboardCard'
import { LoadingState } from '../LoadingState'
import { EventList } from './EventList'

export function RecentEvents() {
  const { events, isInitialLoading, error, refresh } = useRecentEvents()

  return (
    <DashboardCard title="Recent Events" eyebrow="Checkout activity">
      <div className="recent-events">
        {isInitialLoading && events === null ? (
          <LoadingState label="Loading checkout events..." lines={3} />
        ) : null}

        {!isInitialLoading && events === null && error ? (
          <div className="history-notice" role="alert">
            <p>{error}</p>
            <button
              className="button button--secondary"
              type="button"
              aria-label="Retry events"
              onClick={() => void refresh()}
            >
              Retry
            </button>
          </div>
        ) : null}

        {events !== null ? (
          <>
            {error ? (
              <div className="history-notice history-notice--inline" role="alert">
                <p>Unable to refresh checkout events.</p>
                <button
                  className="button button--secondary"
                  type="button"
                  aria-label="Retry events"
                  onClick={() => void refresh()}
                >
                  Retry
                </button>
              </div>
            ) : null}

            {events.length > 0 ? (
              <EventList events={events} />
            ) : (
              <div className="history-empty">
                <strong>No checkout events yet</strong>
                <p>Cart activity will appear here as products cross the zone.</p>
              </div>
            )}
          </>
        ) : null}
      </div>
    </DashboardCard>
  )
}
