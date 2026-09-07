import { Link, useParams } from 'react-router'

import { EventList } from '../components/events/EventList'
import { LoadingState } from '../components/LoadingState'
import { useSessionDetail } from '../hooks/useSessionDetail'
import type { CheckoutSessionDetail } from '../types/history'
import { formatInr } from '../utils/currency'
import { formatDateTime } from '../utils/dateTime'

export function SessionDetailPage() {
  const { sessionId: sessionIdParameter } = useParams()
  const sessionId = parseSessionId(sessionIdParameter)

  if (sessionId === null) {
    return <SessionNotFound />
  }

  // Route parameters can change without remounting this page. Key the detail
  // view so data from the previous session is never shown under a new ID.
  return <ValidSessionDetail key={sessionId} sessionId={sessionId} />
}

function ValidSessionDetail({ sessionId }: { sessionId: number }) {
  const { session, isLoading, error, refresh } = useSessionDetail(sessionId)

  return (
    <div className="page-stack">
      <header className="page-heading session-detail-heading">
        <Link className="text-link" to="/sessions">
          <span aria-hidden="true">←</span>{' '}
          Back to Sessions
        </Link>
        <p className="eyebrow">Checkout history</p>
        <h1>Session #{sessionId}</h1>
        <p>Review the persisted lifecycle and cart events for this session.</p>
      </header>

      {isLoading && session === null ? (
        <section className="dashboard-card" aria-label="Session status">
          <LoadingState label="Loading checkout session..." lines={3} />
        </section>
      ) : null}

      {!isLoading && error === 'not-found' ? <SessionNotFound compact /> : null}

      {!isLoading && error === 'unavailable' ? (
        <section className="dashboard-card" aria-label="Session status">
          <div className="history-notice" role="alert">
            <p>Unable to load checkout session.</p>
            <button
              className="button button--secondary"
              type="button"
              aria-label="Retry session"
              onClick={() => void refresh()}
            >
              Retry
            </button>
          </div>
        </section>
      ) : null}

      {session ? <SessionDetailContent session={session} /> : null}
    </div>
  )
}

function SessionDetailContent({ session }: { session: CheckoutSessionDetail }) {
  const isActive = session.ended_at === null

  return (
    <>
      <section className="dashboard-card session-summary" aria-label="Session summary">
        <dl className="session-summary__grid">
          <div>
            <dt>Started</dt>
            <dd>
              <time dateTime={session.started_at}>
                {formatDateTime(session.started_at)}
              </time>
            </dd>
          </div>
          <div>
            <dt>Ended</dt>
            <dd>
              {session.ended_at ? (
                <time dateTime={session.ended_at}>
                  {formatDateTime(session.ended_at)}
                </time>
              ) : (
                'In progress'
              )}
            </dd>
          </div>
          <div className="session-summary__total">
            <dt>Final total</dt>
            <dd>
              {session.final_total === null
                ? 'Pending'
                : formatInr(session.final_total)}
            </dd>
          </div>
          <div>
            <dt>Status</dt>
            <dd>
              <span
                className={`session-status session-status--${
                  isActive ? 'active' : 'completed'
                }`}
              >
                {isActive ? 'Active' : 'Completed'}
              </span>
            </dd>
          </div>
        </dl>
      </section>

      <section className="dashboard-card session-events">
        <h2>Event History</h2>
        <div className="session-events__content">
          {session.events.length > 0 ? (
            <EventList events={session.events} timestampStyle="full" />
          ) : (
            <p className="empty-copy">
              No events were recorded for this session.
            </p>
          )}
        </div>
      </section>
    </>
  )
}

function SessionNotFound({ compact = false }: { compact?: boolean }) {
  const content = (
    <section className="dashboard-card history-empty">
      <h2>Session not found</h2>
      <p>The requested checkout session is unavailable or does not exist.</p>
      <Link className="text-link" to="/sessions">
        Back to Sessions
      </Link>
    </section>
  )

  if (compact) {
    return content
  }

  return <div className="page-stack session-not-found">{content}</div>
}

function parseSessionId(value: string | undefined): number | null {
  if (!value || !/^[1-9]\d*$/.test(value)) {
    return null
  }
  const sessionId = Number(value)
  return Number.isSafeInteger(sessionId) ? sessionId : null
}
