import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import process from 'node:process'
import { describe, expect, it } from 'vitest'

/**
 * The live site enforces the Content-Security-Policy in vercel.json, which
 * allows the one inline script in index.html by its hash. Editing that script
 * without updating the hash stops it running on every page.
 */

const read = (name) => readFileSync(join(process.cwd(), name), 'utf8')

const policy = JSON.parse(read('vercel.json'))
  .headers.flatMap((rule) => rule.headers)
  .find((header) => header.key === 'Content-Security-Policy').value

describe('content security policy', () => {
  it('allows every inline script in index.html by its hash', () => {
    const inline = [...read('index.html').matchAll(/<script>([\s\S]*?)<\/script>/g)].map((match) => match[1])
    expect(inline.length).toBeGreaterThan(0)
    for (const script of inline) {
      const hash = createHash('sha256').update(script).digest('base64')
      expect(policy).toContain(`'sha256-${hash}'`)
    }
  })

  it('does not allow inline scripts in general', () => {
    const scriptSrc = policy.split(';').find((directive) => directive.trim().startsWith('script-src'))
    expect(scriptSrc).not.toContain('unsafe-inline')
    expect(scriptSrc).not.toContain('unsafe-eval')
  })
})
