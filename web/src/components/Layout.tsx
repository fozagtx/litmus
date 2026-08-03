import {
  IconArchive,
  IconDownload,
  IconFileCheck,
  IconPencil,
} from '@tabler/icons-react';
import { Link, NavLink, Outlet } from 'react-router-dom';

const NAV = [
  { to: '/studio', label: 'Studio', icon: IconPencil },
  { to: '/vault', label: 'Vault', icon: IconArchive },
  { to: '/verify', label: 'Verify', icon: IconFileCheck },
  { to: '/export', label: 'Export', icon: IconDownload },
];

/** Floating primary nav: a rounded rail on the left, vertically centered
 * against the viewport and offset from the screen edge. On small screens it
 * folds back into a top row under the wordmark. */
function SideNav() {
  return (
    <nav
      aria-label="Primary"
      className="fixed left-5 top-1/2 z-40 hidden -translate-y-1/2 flex-col gap-1 rounded-card border border-line bg-white p-2 md:flex print:hidden"
    >
      {NAV.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          className={({ isActive }) =>
            `flex flex-col items-center gap-1 rounded-input px-3 py-2.5 text-13 transition-colors duration-150 ease-out ${
              isActive
                ? 'bg-mono-chip font-medium text-ink'
                : 'text-ink-2 hover:bg-paper hover:text-ink'
            }`
          }
        >
          <item.icon size={20} stroke={1.5} aria-hidden />
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}

export function Layout() {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-line print:hidden">
        <div className="mx-auto flex h-14 w-full max-w-6xl items-center justify-between px-4 sm:px-6">
          <Link to="/" className="font-display text-22 text-ink">
            Litmus
          </Link>
          <nav aria-label="Primary" className="flex items-center gap-5 md:hidden">
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

      <SideNav />

      {/* Reserve room for the floating rail so content never sits under it. */}
      <main className="flex-1 md:pl-28">
        <Outlet />
      </main>

      <footer className="border-t border-line print:hidden">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-2 px-4 py-6 text-13 text-ink-2 sm:flex-row sm:items-center sm:justify-between sm:px-6 md:pl-28">
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
