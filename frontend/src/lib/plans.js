/**
 * The plans as the website and the app show them. The backend's catalogue
 * (backend/app/services/plans.py) is what's charged and enforced; keep the
 * two in step when prices change.
 */
// Outside India the plans are priced in US dollars (about 35% above the
// rupee price). Those are invoiced by email for now - checkout is rupees only.
export const PLANS = [
  { id: 'starter', name: 'Starter', sections: 'Up to 30 sections', maxSections: 30, price: 9999, doneForYou: 17999, usd: 149, doneForYouUsd: 279 },
  { id: 'standard', name: 'Standard', sections: '31 to 50 sections', maxSections: 50, price: 14999, doneForYou: 26999, usd: 229, doneForYouUsd: 399 },
  { id: 'plus', name: 'Plus', sections: '51 to 80 sections', maxSections: 80, price: 19999, doneForYou: 34999, usd: 299, doneForYouUsd: 529 },
]

export const LARGE = {
  id: 'business',
  name: 'Large / Group',
  sections: 'More than 80 sections, or several schools',
  base: 19999,
  perSection: 250,
  from: 80,
  baseUsd: 299,
  perSectionUsd: 4,
}

export const PLAN_NAMES = {
  free: 'Free trial',
  starter: 'Starter',
  standard: 'Standard',
  plus: 'Plus',
  pro: 'Pro',
  business: 'Large / Group',
}

export const EVERY_PLAN = ['Every feature', 'Unlimited people and AI', 'Exports without the watermark', 'Email support']

export const DONE_FOR_YOU =
  'We set it up for you: your staff, subjects, every class’s plan and your first timetable. Covers the first year; it renews at the software price.'

export const inr = (n) => `₹${Number(n).toLocaleString('en-IN')}`

export const usd = (n) => `$${Number(n).toLocaleString('en-US')}`

/**
 * 'INR' for visitors in India, 'USD' everywhere else. Read from the
 * browser's time zone (India has one, Asia/Kolkata), so there's no lookup
 * and nothing is sent anywhere. A choice made with the INR/USD switch on the
 * pricing page wins, and ?currency=usd / inr in the address forces one.
 */
const CURRENCY_KEY = 'timetablz.currency'
export function detectCurrency() {
  if (typeof window === 'undefined') return 'INR'
  try {
    const forced = new URLSearchParams(window.location.search).get('currency')?.toUpperCase()
    if (forced === 'INR' || forced === 'USD') return forced
    const saved = window.localStorage.getItem(CURRENCY_KEY)
    if (saved === 'INR' || saved === 'USD') return saved
  } catch {
    // Storage blocked: fall through to the time zone.
  }
  try {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || ''
    return tz === 'Asia/Kolkata' || tz === 'Asia/Calcutta' ? 'INR' : 'USD'
  } catch {
    return 'INR'
  }
}

export function saveCurrency(c) {
  try {
    window.localStorage.setItem(CURRENCY_KEY, c)
  } catch {
    // Not remembered; it's only a convenience.
  }
}

/** A plan's price in the visitor's currency, formatted. kind: 'software' | 'done_for_you'. */
export function planPrice(plan, currency, kind = 'software') {
  if (currency === 'USD') return usd(kind === 'done_for_you' ? plan.doneForYouUsd : plan.usd)
  return inr(kind === 'done_for_you' ? plan.doneForYou : plan.price)
}

export const largeBase = (currency) => (currency === 'USD' ? usd(LARGE.baseUsd) : inr(LARGE.base))
export const largePerSection = (currency) => (currency === 'USD' ? usd(LARGE.perSectionUsd) : inr(LARGE.perSection))

export const INVOICE_EMAIL = 'support@timetablz.com'
export function invoiceMailto(planName, kind, price, sections) {
  const subject = `Invoice request: ${planName}${kind === 'done_for_you' ? ', done for you' : ''} (${price})`
  const body = `Hello,\n\nPlease send us an invoice for the ${planName} plan${kind === 'done_for_you' ? ' (done for you)' : ''}, ${price} a year.\n\nSchool name:\nCountry:\nNumber of sections: ${sections ?? ''}\nBilling address:\n\nThank you.`
  return `mailto:${INVOICE_EMAIL}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`
}

export const largePrice =(sections) => LARGE.base + LARGE.perSection * Math.max(0, sections - LARGE.from)

/** The smallest plan a school with this many sections fits, or LARGE. */
export function planForSections(sections) {
  return PLANS.find((p) => sections <= p.maxSections) ?? LARGE
}
