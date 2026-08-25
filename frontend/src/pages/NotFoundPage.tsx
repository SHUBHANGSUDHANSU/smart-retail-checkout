import { Link } from 'react-router'

export function NotFoundPage() {
  return (
    <div className="page-stack">
      <header className="page-heading">
        <p className="eyebrow">404</p>
        <h1>Page not found</h1>
        <p>The requested operator-dashboard page does not exist.</p>
      </header>
      <Link className="text-link" to="/">
        Return to Dashboard
      </Link>
    </div>
  )
}
