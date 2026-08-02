import { Link, NavLink, Outlet } from 'react-router-dom';

const NAV = [
  { to: '/studio', label: 'Studio' },
  { to: '/vault', label: 'Vault' },
  { to: '/verify', label: 'Verify' },
  { to: '/export', label: 'Export' },
];

export function Layout() {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-line print:hidden">
        <div className="mx-auto flex h-14 w-full max-w-6xl items-center justify-between px-4 sm:px-6">
          <Link to="/" className="font-display text-22 text-ink">
            Litmus
          </Link>
          <nav aria-label="Primary" className="flex items-center gap-5">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `text-15 transition-colors duration-150 ease-out ${
                    isActive ? 'font-medium text-ink' : 'text-ink-2 hover:text-ink'
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      <main className="flex-1">
        <Outlet />
      </main>

      <footer className="border-t border-line print:hidden">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-2 px-4 py-6 text-13 text-ink-2 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p>Built on Backblaze B2 Object Lock and the Genblaze pipeline SDK.</p>
          <div className="flex items-center gap-4">
            <a
              href="https://github.com/fozagtx/litmus"
              target="_blank"
              rel="noreferrer"
              className="transition-colors duration-150 ease-out hover:text-ink"
            >
              GitHub
            </a>
            <a
              href="https://github.com/fozagtx/litmus#how-it-works"
              target="_blank"
              rel="noreferrer"
              className="transition-colors duration-150 ease-out hover:text-ink"
            >
              How sealing works
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
