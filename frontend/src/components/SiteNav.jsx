import { getToken } from '../api'

/**
 * The public site's top bar - the same one on the homepage and every page
 * reached from it (Why Timetablz, Pricing, Customers, About, Support and the
 * legal pages), so moving between them never loses the navigation. The
 * wordmark goes home; there is no separate "Back to home".
 *
 * The inner pages are full page loads that render before the app has checked
 * who is signed in, so `signedIn` defaults to whether a session token is
 * saved - enough to show "Open app" rather than "Sign in" to someone who is.
 */

export const NAV_LINKS = [
  { id: 'why', label: 'Why Timetablz', href: '?page=why' },
  { id: 'pricing', label: 'Plans and Pricing', href: '?page=pricing' },
  { id: 'customers', label: 'Customers', href: '?page=customers' },
  { id: 'about', label: 'About', href: '?page=about' },
  { id: 'support', label: 'Support', href: '?page=support' },
]

const go = (query) => window.location.assign(`${window.location.pathname}${query}`)

export default function SiteNav({ current = null, signedIn, onGetStarted, onSignIn }) {
  const isSignedIn = signedIn ?? Boolean(getToken())
  const getStarted = onGetStarted ?? (() => go(isSignedIn ? '?start=app' : '?start=plans'))
  const signIn = onSignIn ?? (() => go('?start=auth'))

  return (
    <div className="sticky top-0 z-30 border-b border-white/10 bg-black">
      <div className="flex items-center px-8 py-4 md:px-16 lg:px-28">
        <div className="flex items-center gap-10">
          <a href={window.location.pathname} className="text-[19px] font-bold tracking-tight text-white">
            Timetablz
          </a>
          <nav aria-label="Site" className="hidden items-center gap-8 text-[15px] text-neutral-300 md:flex">
            {NAV_LINKS.map((link) => (
              <a
                key={link.id}
                href={link.href}
                aria-current={current === link.id ? 'page' : undefined}
                className={current === link.id ? 'font-medium text-white' : 'hover:text-white'}
              >
                {link.label}
              </a>
            ))}
          </nav>
        </div>
        <div className="ml-auto flex items-center gap-6">
          {!isSignedIn && (
            <button onClick={signIn} className="text-[15px] font-medium text-neutral-300 hover:text-white">
              Sign in
            </button>
          )}
          <button
            onClick={getStarted}
            className="rounded-md bg-white px-4 py-2 text-[15px] font-medium text-black hover:bg-neutral-200"
          >
            {isSignedIn ? 'Open app' : 'Get started free'}
          </button>
        </div>
      </div>
    </div>
  )
}
