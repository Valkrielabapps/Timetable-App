// The public site's pages and their addresses.
//
// Each page has its own path (/pricing, /about ...) so search engines and AI
// assistants see separate pages with their own titles - not one URL with a
// ?page= on the end, which they tend to fold into the homepage. Old ?page=
// links still work (and vercel.json redirects them to the path).
//
// The same list drives the build-time prerender (scripts/prerender.mjs), which
// writes each page's HTML so crawlers that don't run JavaScript can read it.
export const SITE_URL = 'https://timetablz.com'

export const PAGE_PATHS = {
  why: '/why-timetablz',
  pricing: '/pricing',
  customers: '/customers',
  about: '/about',
  support: '/support',
  contact: '/contact',
  privacy: '/privacy',
  terms: '/terms',
  refunds: '/refunds',
}

export function pagePath(id) {
  return PAGE_PATHS[id] || '/'
}

/** Which public page this address is for, or null for the homepage/app. */
export function pageFromLocation(location) {
  const query = new URLSearchParams(location.search).get('page')
  if (query) return query
  const path = location.pathname.replace(/\/+$/, '') || '/'
  for (const [id, p] of Object.entries(PAGE_PATHS)) if (p === path) return id
  return null
}
