import { useEffect, useState } from 'react'
import { getToken } from '../api'

/**
 * The public site's top bar - the same one on the homepage and every page
 * reached from it (Why Timetablz, Pricing, Customers, About, Support and the
 * legal pages), so moving between them never loses the navigation. The
 * wordmark goes home; there is no separate "Back to home".
 *
 * Wide screens show the links inline. Below laptop width they would wrap
 * onto two lines, so they move into a menu behind a button instead - which
 * is also the only way a phone visitor reaches Pricing or About.
 *
 * The inner pages are full page loads that render before the app has checked
 * who is signed in, so `signedIn` defaults to whether a session token is
 * saved - enough to show "Open app" rather than "Sign in" to someone who is.
 */

export const NAV_LINKS = [
  { id: 'why', label: 'Why Timetablz', href: '?page=why' },
  { id: 'pricing', label: 'Pricing', href: '?page=pricing' },
  { id: 'customers', label: 'Customers', href: '?page=customers' },
  { id: 'about', label: 'About', href: '?page=about' },
  { id: 'support', label: 'Support', href: '?page=support' },
]

const go = (query) => window.location.assign(`${window.location.pathname}${query}`)

export default function SiteNav({ current = null, signedIn, onGetStarted, onSignIn }) {
  const isSignedIn = signedIn ?? Boolean(getToken())
  const getStarted = onGetStarted ?? (() => go(isSignedIn ? '?start=app' : '?start=plans'))
  const signIn = onSignIn ?? (() => go('?start=auth'))
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    if (!menuOpen) return undefined
    const onKey = (e) => e.key === 'Escape' && setMenuOpen(false)
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [menuOpen])

  return (
    <div className="sticky top-0 z-30 border-b border-white/10 bg-black">
      <div className="flex items-center px-6 py-4 md:px-10 xl:px-28">
        <div className="flex items-center gap-10">
          <a href={window.location.pathname} className="whitespace-nowrap text-[19px] font-bold tracking-tight text-white">
            Timetablz
          </a>
          <nav aria-label="Site" className="hidden items-center gap-7 text-[15px] text-neutral-300 lg:flex">
            {NAV_LINKS.map((link) => (
              <a
                key={link.id}
                href={link.href}
                aria-current={current === link.id ? 'page' : undefined}
                className={`whitespace-nowrap ${current === link.id ? 'font-medium text-white' : 'hover:text-white'}`}
              >
                {link.label}
              </a>
            ))}
          </nav>
        </div>

        <div className="ml-auto flex items-center gap-5">
          {!isSignedIn && (
            <button
              onClick={signIn}
              className="hidden whitespace-nowrap text-[15px] font-medium text-neutral-300 hover:text-white sm:block"
            >
              Sign in
            </button>
          )}
          <button
            onClick={getStarted}
            className="whitespace-nowrap rounded-md bg-white px-4 py-2 text-[15px] font-medium text-black hover:bg-neutral-200"
          >
            {isSignedIn ? 'Open app' : 'Get started free'}
          </button>
          <button
            type="button"
            onClick={() => setMenuOpen((v) => !v)}
            aria-expanded={menuOpen}
            aria-controls="site-menu"
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            className="-mr-2 rounded-md p-2 text-neutral-300 hover:bg-white/10 hover:text-white lg:hidden"
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              {menuOpen ? <path d="M6 6l12 12M18 6 6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
            </svg>
          </button>
        </div>
      </div>

      {menuOpen && (
        <nav id="site-menu" aria-label="Site menu" className="border-t border-white/10 bg-black px-6 pb-6 pt-2 lg:hidden">
          <ul className="flex flex-col">
            {NAV_LINKS.map((link) => (
              <li key={link.id}>
                <a
                  href={link.href}
                  aria-current={current === link.id ? 'page' : undefined}
                  className={`block border-b border-white/10 py-3.5 text-base ${
                    current === link.id ? 'font-medium text-white' : 'text-neutral-300 hover:text-white'
                  }`}
                >
                  {link.label}
                </a>
              </li>
            ))}
          </ul>
          {!isSignedIn && (
            <button
              onClick={signIn}
              className="mt-5 w-full rounded-md border border-white/25 py-2.5 text-[15px] font-medium text-white hover:bg-white/5"
            >
              Sign in
            </button>
          )}
        </nav>
      )}
    </div>
  )
}
