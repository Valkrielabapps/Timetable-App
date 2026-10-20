/**
 * The public site's footer - the same one on the homepage and every page
 * reached from it, so each page ends the same way it starts (SiteNav).
 */
// Every link here goes somewhere real — an in-page anchor already used
// elsewhere on this page, a mailto, or one of the two legal pages built
// in LegalPage.jsx/PrivacyPolicyPage.jsx/TermsOfServicePage.jsx.
// Deliberately NOT padded out with Papermark's full column count (Use
// Cases, Alternatives, a blog, a help center, comparison pages, ...) —
// this site doesn't have any of that content, and a footer full of links
// to pages that don't exist would look broken rather than substantial.
const FOOTER_COLUMNS = [
  {
    // "How it works" link removed along with that section (see the render
    // comment above HowItWorks) — add back once it's wanted again. Pricing
    // now points at the standalone PricingPage.jsx (`?page=pricing`)
    // instead of the removed in-page `#pricing` anchor.
    heading: 'Product',
    links: [
      { label: 'Why Timetablz', href: '?page=why' },
      { label: 'Pricing', href: '?page=pricing' },
    ],
  },
  {
    // No "Contact us" mailto here yet — the business email/domain hasn't
    // been decided (see the founder conversation on domain naming), and a
    // mailto to a made-up address would silently bounce. Add it back once
    // that's settled.
    heading: 'Company',
    links: [
      { label: 'About', href: '?page=about' },
      { label: 'Customers', href: '?page=customers' },
      { label: 'Support', href: '?page=support' },
    ],
  },
  {
    heading: 'Legal',
    links: [
      { label: 'Privacy policy', href: '?page=privacy' },
      { label: 'Terms of service', href: '?page=terms' },
      { label: 'Refunds and cancellations', href: '?page=refunds' },
      { label: 'Contact us', href: '?page=contact' },
    ],
  },
]

export default function SiteFooter() {
  return (
    <footer className="border-t border-white/10 bg-black py-16 text-neutral-400">
      <div className="mx-auto max-w-6xl px-6">
        <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-[1.3fr_1fr_1fr_1fr]">
          <div>
            <span className="text-[17px] font-bold tracking-tight text-white">Timetablz</span>
            <p className="mt-3 max-w-[220px] text-sm leading-relaxed">
              Instant, clash-free timetables for schools and colleges.
            </p>
            <a href="mailto:support@timetablz.com" className="mt-4 block text-sm text-neutral-300 hover:text-white">
              support@timetablz.com
            </a>
            <p className="mt-1 text-sm">Kerala, India</p>
          </div>

          {FOOTER_COLUMNS.map((col) => (
            <div key={col.heading}>
              <p className="text-sm font-semibold text-white">{col.heading}</p>
              <ul className="mt-4 space-y-3 text-sm">
                {col.links.map((link) => (
                  <li key={link.label}>
                    <a href={link.href} className="hover:text-white">
                      {link.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-14 border-t border-white/10 pt-6 text-xs">
          © {new Date().getFullYear()} Timetablz. All rights reserved.
        </div>
      </div>
    </footer>
  )
}
