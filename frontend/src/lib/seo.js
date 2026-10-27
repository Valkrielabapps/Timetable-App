// What search engines and AI assistants are told about each public page:
// title, description and structured data (schema.org JSON-LD). Used by the
// build-time prerender (scripts/prerender.mjs), which writes these into each
// page's HTML head.
//
// Keep descriptions true and specific - they are what Google shows under the
// link, and what an AI assistant quotes when it recommends Timetablz.
import { PAGE_PATHS, SITE_URL } from './sitePages.js'

const BRAND = 'Timetablz'

export const PAGE_META = {
  home: {
    path: '/',
    title: 'Timetablz | School Timetable Software and Automatic Timetable Generator',
    description:
      'Timetablz builds clash-free school timetables automatically. Type your rules in plain English, and get a timetable for every class and teacher, with substitutions, locked periods and PDF exports. Free for 14 days.',
  },
  why: {
    title: 'Why Timetablz | Automatic Timetables Without the Spreadsheet',
    description:
      'Why schools switch from spreadsheets and manual timetabling to Timetablz: rules in plain English, a clash-free timetable in minutes, and a clear reason when a rule makes one impossible.',
  },
  pricing: {
    title: 'Pricing | Timetablz School Timetable Software',
    description:
      'Timetablz pricing: free for 14 days (up to 5 sections), Pro at ₹4,999 a year for up to 60 sections and 5 staff, and Business plans for larger schools and school groups.',
  },
  customers: {
    title: 'Customers | Schools Using Timetablz',
    description: 'Schools that build their timetables with Timetablz, and what changed for them.',
  },
  about: {
    title: 'About Timetablz | School Timetable Software Made in India',
    description:
      'Timetablz is a small team in India building timetable software for schools and colleges: automatic, clash-free timetables from rules written in plain English.',
  },
  support: {
    title: 'Support and FAQ | Timetablz',
    description:
      'Answers to common questions about setting up your school, generating timetables, substitutions, billing and data on Timetablz, and how to reach the team.',
  },
  contact: {
    title: 'Contact Timetablz | Book a Demo',
    description: 'Email the Timetablz team at support@timetablz.com for a demo, help with your timetable, or billing questions.',
  },
  privacy: { title: 'Privacy Policy | Timetablz', description: 'How Timetablz collects, uses and protects your school\'s data.' },
  terms: { title: 'Terms of Service | Timetablz', description: 'The terms for using Timetablz timetable software.' },
  refunds: {
    title: 'Refund and Cancellation Policy | Timetablz',
    description: 'How refunds and cancellations work for Timetablz plans, including pro-rata refunds of unused months.',
  },
}
for (const [id, path] of Object.entries(PAGE_PATHS)) if (PAGE_META[id]) PAGE_META[id].path = path

export function canonicalUrl(id) {
  const path = PAGE_META[id]?.path || '/'
  return `${SITE_URL}${path === '/' ? '/' : path}`
}

const ORGANIZATION = {
  '@type': 'Organization',
  '@id': `${SITE_URL}/#organization`,
  name: BRAND,
  url: `${SITE_URL}/`,
  logo: `${SITE_URL}/apple-touch-icon.png`,
  email: 'support@timetablz.com',
  address: { '@type': 'PostalAddress', addressLocality: 'Chennai', addressRegion: 'Tamil Nadu', addressCountry: 'IN' },
  contactPoint: {
    '@type': 'ContactPoint',
    contactType: 'customer support',
    email: 'support@timetablz.com',
    availableLanguage: ['English'],
  },
}

const SOFTWARE = {
  '@type': 'SoftwareApplication',
  '@id': `${SITE_URL}/#software`,
  name: BRAND,
  url: `${SITE_URL}/`,
  applicationCategory: 'EducationalApplication',
  applicationSubCategory: 'School timetable software',
  operatingSystem: 'Web browser',
  description: PAGE_META.home.description,
  publisher: { '@id': `${SITE_URL}/#organization` },
  featureList: [
    'Automatic clash-free timetable generation for every class, section and teacher',
    'Scheduling rules written in plain English',
    'Built-in limits on teachers’ periods per day and per week',
    'Elective blocks, lab batches and double periods',
    'Lock or freeze parts of a timetable and regenerate the rest',
    'Teacher absence and substitution planning',
    'Timetable versions you can open, rename and compare',
    'PDF and Excel exports for classes and teachers',
    'Explains which rule makes a timetable impossible',
  ],
  offers: [
    {
      '@type': 'Offer',
      name: 'Free',
      price: '0',
      priceCurrency: 'INR',
      description: '14 days free, up to 5 sections, no card needed',
    },
    {
      '@type': 'Offer',
      name: 'Pro',
      price: '4999',
      priceCurrency: 'INR',
      description: 'Per school per year: up to 60 sections and 5 staff',
    },
  ],
}

function faqPage(items) {
  return {
    '@type': 'FAQPage',
    mainEntity: items.map(({ q, a }) => ({
      '@type': 'Question',
      name: q,
      acceptedAnswer: { '@type': 'Answer', text: a },
    })),
  }
}

/** schema.org graph for a page, given any FAQs shown on it. */
export function structuredData(id, faqs = []) {
  const graph = [ORGANIZATION]
  if (id === 'home') {
    graph.push({
      '@type': 'WebSite',
      '@id': `${SITE_URL}/#website`,
      name: BRAND,
      url: `${SITE_URL}/`,
      publisher: { '@id': `${SITE_URL}/#organization` },
    })
    graph.push(SOFTWARE)
  }
  if (id === 'pricing') graph.push(SOFTWARE)
  if (faqs.length) graph.push(faqPage(faqs))
  if (id !== 'home') {
    graph.push({
      '@type': 'BreadcrumbList',
      itemListElement: [
        { '@type': 'ListItem', position: 1, name: BRAND, item: `${SITE_URL}/` },
        { '@type': 'ListItem', position: 2, name: PAGE_META[id].title.split(' | ')[0], item: canonicalUrl(id) },
      ],
    })
  }
  return { '@context': 'https://schema.org', '@graph': graph }
}
