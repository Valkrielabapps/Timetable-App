// Build-time only: renders each public page to HTML, so search engines and AI
// crawlers that don't run JavaScript still read the page's words. Bundled by
// `vite build --ssr src/prerender.jsx` and used by scripts/prerender.mjs; the
// browser never loads this file. In the browser, main.jsx renders the app over
// this HTML as before.
import { renderToString } from 'react-dom/server'
import LandingPage from './components/LandingPage.jsx'
import PricingPage, { BILLING_FAQS } from './components/PricingPage.jsx'
import WhyTimetablzPage from './components/WhyTimetablzPage.jsx'
import AboutPage from './components/AboutPage.jsx'
import CustomersPage from './components/CustomersPage.jsx'
import SupportPage, { FAQ_GROUPS } from './components/SupportPage.jsx'
import ContactPage from './components/ContactPage.jsx'
import PrivacyPolicyPage from './components/PrivacyPolicyPage.jsx'
import TermsOfServicePage from './components/TermsOfServicePage.jsx'
import RefundPolicyPage from './components/RefundPolicyPage.jsx'
import { canonicalUrl, PAGE_META, structuredData } from './lib/seo.js'

const noop = () => {}
const nav = { onBack: noop, onGetStarted: noop }

const PAGES = {
  home: () => <LandingPage onGetStarted={noop} onSignIn={noop} />,
  why: () => <WhyTimetablzPage {...nav} />,
  pricing: () => <PricingPage {...nav} />,
  customers: () => <CustomersPage {...nav} />,
  about: () => <AboutPage {...nav} />,
  support: () => <SupportPage {...nav} />,
  contact: () => <ContactPage onBack={noop} />,
  privacy: () => <PrivacyPolicyPage onBack={noop} />,
  terms: () => <TermsOfServicePage onBack={noop} />,
  refunds: () => <RefundPolicyPage onBack={noop} />,
}

const FAQS = {
  pricing: BILLING_FAQS,
  support: FAQ_GROUPS.flatMap((g) => g.items),
}

export function pages() {
  return Object.keys(PAGES).map((id) => ({
    id,
    path: PAGE_META[id].path,
    title: PAGE_META[id].title,
    description: PAGE_META[id].description,
    canonical: canonicalUrl(id),
    jsonLd: structuredData(id, FAQS[id] || []),
    html: renderToString(PAGES[id]()),
  }))
}
