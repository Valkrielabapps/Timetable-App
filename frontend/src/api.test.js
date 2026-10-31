import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'

/** How a refused request reads to the person who made it. */

const respond = (status, body) =>
  vi.spyOn(globalThis, 'fetch').mockResolvedValue({
    ok: false, status, statusText: 'Error', headers: new Headers(), json: async () => body,
  })

afterEach(() => vi.restoreAllMocks())

describe('error messages', () => {
  it('shows a validation error as its sentence, not JSON', async () => {
    respond(422, { detail: [{ type: 'value_error', loc: ['body', 'password'], msg: 'Value error, Use at least 8 characters for your password.' }] })
    await expect(api.signup({ email: 'a@a.com', password: 'short', name: 'A' })).rejects.toThrow('422 Use at least 8 characters for your password.')
  })

  it('keeps a plain message as it is', async () => {
    respond(400, { detail: 'An account with this email already exists' })
    await expect(api.signup({ email: 'a@a.com', password: 'password123', name: 'A' })).rejects.toThrow('400 An account with this email already exists')
  })
})
