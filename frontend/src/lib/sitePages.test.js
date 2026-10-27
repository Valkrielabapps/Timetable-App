import { describe, expect, it } from 'vitest'
import { pageFromLocation } from './sitePages'
import { canonicalUrl, PAGE_META, structuredData } from './seo'

const at = (pathname, search = '') => ({ pathname, search })

describe('public page addresses', () => {
  it('reads the page from its own path', () => {
    expect(pageFromLocation(at('/pricing'))).toBe('pricing')
    expect(pageFromLocation(at('/why-timetablz/'))).toBe('why')
    expect(pageFromLocation(at('/'))).toBe(null)
    expect(pageFromLocation(at('/admin'))).toBe(null)
  })

  it('still understands old ?page= links', () => {
    expect(pageFromLocation(at('/', '?page=about'))).toBe('about')
    expect(pageFromLocation(at('/', '?page=payment-status&order_id=x'))).toBe('payment-status')
  })

  it('gives every page a title, description and canonical address', () => {
    for (const [id, meta] of Object.entries(PAGE_META)) {
      expect(meta.title.length).toBeGreaterThan(10)
      expect(meta.description.length).toBeLessThanOrEqual(230)
      expect(canonicalUrl(id)).toMatch(/^https:\/\/timetablz\.com\//)
    }
    expect(canonicalUrl('pricing')).toBe('https://timetablz.com/pricing')
  })

  it('describes the product and its price for search engines', () => {
    const graph = structuredData('pricing', [{ q: 'Q?', a: 'A.' }])['@graph']
    const app = graph.find((n) => n['@type'] === 'SoftwareApplication')
    expect(app.offers.find((o) => o.name === 'Pro').price).toBe('4999')
    expect(graph.find((n) => n['@type'] === 'FAQPage').mainEntity).toHaveLength(1)
  })
})
