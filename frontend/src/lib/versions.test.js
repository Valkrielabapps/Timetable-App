import { describe, expect, it } from 'vitest'
import { pickVersions, versionLabel } from './versions'

const v = (id, status, extra = {}) => ({ id, status, version_number: id, ...extra })

describe('which version to show', () => {
  it('shows the current version, not simply the newest', () => {
    const r = pickVersions([v(1, 'draft', { is_current: true }), v(2, 'draft')])
    expect(r.shownId).toBe(1)
    expect(r.current.id).toBe(1)
  })

  it('shows a generation while it runs', () => {
    expect(pickVersions([v(1, 'draft', { is_current: true }), v(2, 'generating')]).shownId).toBe(2)
  })

  it('keeps the current version on screen after a failed attempt, and reports the failure', () => {
    const r = pickVersions([v(1, 'draft', { is_current: true }), v(2, 'failed')])
    expect(r.shownId).toBe(1)
    expect(r.failure.id).toBe(2)
  })

  it('a failure older than the current version is not reported', () => {
    expect(pickVersions([v(1, 'failed'), v(2, 'draft', { is_current: true })]).failure).toBeNull()
  })

  it('falls back to the newest finished version when none is marked current', () => {
    expect(pickVersions([v(1, 'draft'), v(3, 'draft'), v(2, 'failed')]).current.id).toBe(3)
  })

  it('labels versions by number and name', () => {
    expect(versionLabel(v(3, 'draft'))).toBe('Version 3')
    expect(versionLabel(v(3, 'draft', { name: 'Grades 1-5 approved' }))).toBe('Version 3 · Grades 1-5 approved')
  })
})
