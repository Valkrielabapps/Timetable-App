/**
 * The plans as the website and the app show them. The backend's catalogue
 * (backend/app/services/plans.py) is what's charged and enforced; keep the
 * two in step when prices change.
 */
export const PLANS = [
  { id: 'starter', name: 'Starter', sections: 'Up to 30 sections', maxSections: 30, price: 9999, doneForYou: 17999 },
  { id: 'standard', name: 'Standard', sections: '31 to 50 sections', maxSections: 50, price: 14999, doneForYou: 26999 },
  { id: 'plus', name: 'Plus', sections: '51 to 80 sections', maxSections: 80, price: 19999, doneForYou: 34999 },
]

export const LARGE = {
  id: 'business',
  name: 'Large / Group',
  sections: 'More than 80 sections, or several schools',
  base: 19999,
  perSection: 250,
  from: 80,
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

export const largePrice = (sections) => LARGE.base + LARGE.perSection * Math.max(0, sections - LARGE.from)

/** The smallest plan a school with this many sections fits, or LARGE. */
export function planForSections(sections) {
  return PLANS.find((p) => sections <= p.maxSections) ?? LARGE
}
