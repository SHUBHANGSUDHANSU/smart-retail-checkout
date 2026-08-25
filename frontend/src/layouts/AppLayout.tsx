import { NavLink, Outlet } from 'react-router'

const navigation = [
  { label: 'Dashboard', to: '/' },
  { label: 'Sessions', to: '/sessions' },
  { label: 'System', to: '/system' },
]

export function AppLayout() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <header className="brand-block">
          <span className="brand-mark" aria-hidden="true">
            SR
          </span>
          <div>
            <p className="brand-name">Smart Retail Checkout</p>
            <p className="brand-caption">Operations console</p>
          </div>
        </header>
        <nav aria-label="Primary navigation" className="primary-nav">
          {navigation.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                `nav-link${isActive ? ' nav-link--active' : ''}`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="main-content">
        <Outlet />
      </main>
    </div>
  )
}
