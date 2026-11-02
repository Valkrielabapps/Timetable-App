import { useState } from 'react'
import { api } from '../api'

/**
 * "Send to Timetablz support": the school's whole setup as it is now, with
 * what they were looking at (`context`) and an optional note, goes to the
 * Timetablz team (POST /schools/{id}/support-snapshot). Shown where a school
 * is stuck: a failed generation, a move that can't be made.
 */
export default function SendToSupport({ schoolId, context = {}, compact = false }) {
  const [open, setOpen] = useState(false)
  const [message, setMessage] = useState('')
  const [state, setState] = useState('idle') // idle | sending | sent | error
  const [error, setError] = useState(null)

  if (!schoolId || !api.sendToSupport) return null

  async function send(e) {
    e?.preventDefault()
    setState('sending')
    setError(null)
    try {
      await api.sendToSupport(schoolId, message.trim(), context)
      setState('sent')
    } catch (err) {
      setError(err.message)
      setState('error')
    }
  }

  if (state === 'sent') {
    return (
      <p className="text-xs text-emerald-700" role="status">
        Sent. The Timetablz team has your setup and will reply to your email.
      </p>
    )
  }
  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={`w-fit text-xs font-medium text-slate-700 underline hover:text-neutral-900 ${compact ? '' : 'mt-1'}`}
      >
        Stuck? Send this to Timetablz support
      </button>
    )
  }
  return (
    <form onSubmit={send} className="flex flex-col gap-2 rounded-md border border-slate-200 bg-slate-50 p-3" aria-label="Send to support">
      <p className="text-xs text-slate-600">
        We&rsquo;ll get a copy of your school&rsquo;s setup (periods, sections, subjects, teachers and rules) as it is now,
        and what you were looking at. Add anything that helps:
      </p>
      <textarea
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        rows={2}
        maxLength={3000}
        placeholder="What were you trying to do? (optional)"
        aria-label="Message to support"
        className="w-full rounded border border-slate-300 bg-white px-2 py-1 text-sm"
      />
      {error && <p className="text-xs text-red-600">{error}</p>}
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={state === 'sending'}
          className="rounded bg-neutral-900 px-3 py-1 text-xs font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
        >
          {state === 'sending' ? 'Sending…' : 'Send to support'}
        </button>
        <button type="button" onClick={() => setOpen(false)} className="rounded border border-slate-300 px-3 py-1 text-xs font-medium hover:bg-white">
          Cancel
        </button>
      </div>
    </form>
  )
}
