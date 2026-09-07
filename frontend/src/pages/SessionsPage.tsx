import { Link } from 'react-router'

import { DashboardCard } from '../components/DashboardCard'
import { LoadingState } from '../components/LoadingState'
import { useSessions } from '../hooks/useSessions'
import type { CheckoutSession } from '../types/history'
import { formatInr } from '../utils/currency'
import { formatDateTime } from '../utils/dateTime'

export function SessionsPage() {
  const { sessions, isLoading, error, refresh } = useSessions()

  return (
    <div className="page-stack">
      <header className="page-heading">
        <p className="eyebrow">Checkout history</p>
        <h1>Checkout Sessions</h1>
        <p>Review persisted checkout runs and open their event history.</p>
      </header>
      <DashboardCard title="Sessions" eyebrow="Recent records">
        <div className="session-history">
          {isLoading && sessions === null ? (
            <LoadingState label="Loading checkout sessions..." lines={4} />
          ) : null}

          {!isLoading && error ? (
            <div className="history-notice" role="alert">
              <p>{error}</p>
              <button
                className="button button--secondary"
                type="button"
                aria-label="Retry sessions"
                onClick={() => void refresh()}
              >
                Retry
              </button>
            </div>
          ) : null}

          {!isLoading && !error && sessions?.length === 0 ? (
            <div className="history-empty">
              <strong>No checkout sessions yet</strong>
              <p>Completed and active application sessions will appear here.</p>
            </div>
          ) : null}

          {sessions && sessions.length > 0 ? (
            <SessionTable sessions={sessions} />
          ) : null}
        </div>
      </DashboardCard>
    </div>
  )
}

function SessionTable({ sessions }: { sessions: CheckoutSession[] }) {
  return (
    <div className="session-table-wrap">
      <table className="session-table">
        <caption className="sr-only">Recent checkout sessions</caption>
        <thead>
          <tr>
            <th scope="col">Session</th>
            <th scope="col">Started</th>
            <th scope="col">Ended</th>
            <th scope="col">Final total</th>
            <th scope="col">Status</th>
          </tr>
        </thead>
        <tbody>
          {sessions.map((session) => {
            const isActive = session.ended_at === null
            return (
              <tr key={session.id}>
                <th scope="row">
                  <Link className="session-link" to={`/sessions/${session.id}`}>
                    Session #{session.id}
                    <span className="session-link__arrow" aria-hidden="true">
                      ↗
                    </span>
                  </Link>
                </th>
                <td data-label="Started">
                  <time dateTime={session.started_at}>
                    {formatDateTime(session.started_at)}
                  </time>
                </td>
                <td data-label="Ended">
                  {session.ended_at ? (
                    <time dateTime={session.ended_at}>
                      {formatDateTime(session.ended_at)}
                    </time>
                  ) : (
                    <span aria-label="Not ended">—</span>
                  )}
                </td>
                <td className="session-table__amount" data-label="Final total">
                  {session.final_total === null ? (
                    <span aria-label="Final total pending">—</span>
                  ) : (
                    formatInr(session.final_total)
                  )}
                </td>
                <td data-label="Status">
                  <span
                    className={`session-status session-status--${
                      isActive ? 'active' : 'completed'
                    }`}
                  >
                    {isActive ? 'Active' : 'Completed'}
                  </span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
