import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import process from 'node:process'
import { describe, expect, it } from 'vitest'

/**
 * Everything in the frontend ships to every visitor's browser, VITE_ variables
 * included (Vite inlines them at build time). Secret keys live only in the
 * backend, and the browser reaches third parties through our own /api, never
 * directly with a key.
 */

const root = process.cwd()
const read = (name) => readFileSync(join(root, name), 'utf8')

function filesUnder(dir) {
  return readdirSync(join(root, dir)).flatMap((name) => {
    const path = join(dir, name)
    return statSync(join(root, path)).isDirectory() ? filesUnder(path) : [path]
  })
}

const source = filesUnder('src').filter((f) => /\.(jsx?|css|html)$/.test(f) && !/\.test\./.test(f))
const envFiles = readdirSync(root).filter((f) => f.startsWith('.env'))

describe('no secrets in the frontend', () => {
  it('names no VITE_ variable like a secret', () => {
    const names = new Set()
    for (const file of [...source, ...envFiles]) {
      for (const [name] of read(file).matchAll(/VITE_[A-Z0-9_]+/g)) names.add(name)
    }
    expect(names.size).toBeGreaterThan(0)
    const secretLooking = [...names].filter((n) => /SECRET|PRIVATE|PASSWORD|API_KEY|TOKEN|DATABASE/.test(n))
    expect(secretLooking).toEqual([])
  })

  it('holds no key-shaped strings', () => {
    const keyShaped = /sk-ant-|sk-[A-Za-z0-9]{20}|AIza[0-9A-Za-z_-]{30}|cfsk_|whsec_|re_[A-Za-z0-9]{24}|postgres(ql)?:\/\/[^\s'"]*:[^\s'"@]+@|-----BEGIN [A-Z ]*PRIVATE KEY/
    const found = [...source, ...envFiles].filter((file) => keyShaped.test(read(file)))
    expect(found).toEqual([])
  })

  it('sends every request through our own backend', () => {
    const direct = source
      .filter((file) => relative('src', file) !== 'api.js')
      .filter((file) => /\bfetch\(|XMLHttpRequest|axios/.test(read(file)))
    expect(direct).toEqual([])
    expect(read('src/api.js')).not.toMatch(/fetch\(\s*['"`]https?:/)
  })
})
