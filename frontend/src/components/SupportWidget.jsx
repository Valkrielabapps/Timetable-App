import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { api } from '../api'

/**
 * Floating help button, bottom-right of every signed-in screen. Clicking it
 * opens a small menu:
 *
 *   - Raise a support ticket: a form that's emailed to the support inbox
 *     (POST /api/support/tickets; Reply-To is the user, so replies go
 *     straight back to them).
 *   - Help & FAQ: the public Support page, in a new tab.
 *   - Schedule a call: opens BOOKING_URL when one is set. Until then it
 *     opens the ticket form pre-filled as a call request, so it still does
 *     something useful.
 *
 * If the ticket can't be sent (email not configured, or Resend is down)
 * the form says so and shows the address to write to, rather than
 * claiming it went through.
 */

// Paste your Calendly / Google Calendar booking link here when you have one.
const BOOKING_URL = ''
const SUPPORT_EMAIL = 'support@timetablz.com'

const CATEGORIES = [
  { value: 'question', label: 'A question' },
  { value: 'problem', label: 'Something is broken' },
  { value: 'feature', label: 'Feature request' },
  { value: 'billing', label: 'Billing' },
  { value: 'other', label: 'Other' },
]

export default function SupportWidget({ schoolId }) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [form, setForm] = useState(null) // null | { category, subject, message }
  const menuRef = useRef(null)

  useEffect(() => {
    if (!menuOpen) return undefined
    function onDown(e) {
      if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false)
    }
    function onKey(e) {
      if (e.key === 'Escape') setMenuOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [menuOpen])

  function openTicket(preset = {}) {
    setMenuOpen(false)
    setForm({ category: 'question', subject: '', message: '', ...preset })
  }

  function scheduleCall() {
    if (BOOKING_URL) {
      setMenuOpen(false)
      window.open(BOOKING_URL, '_blank', 'noopener,noreferrer')
    } else {
      openTicket({
        category: 'other',
        subject: 'Please schedule a call',
        message: 'Best days and times to reach me:\n\nPhone number (optional):\n\nWhat I would like to discuss:\n',
      })
    }
  }

  return (
    <>
      <div ref={menuRef} className="fixed bottom-5 right-5 z-40 flex flex-col items-end gap-3">
        <AnimatePresence>
          {menuOpen && (
            <motion.div
              initial={{ opacity: 0, y: 8, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 8, scale: 0.98 }}
              transition={{ duration: 0.15, ease: 'easeOut' }}
              role="menu"
              className="w-72 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl"
            >
              <div className="border-b border-slate-100 px-4 py-3">
                <p className="text-sm font-semibold">Need help?</p>
                <p className="mt-0.5 text-xs text-slate-500">We usually reply within one working day.</p>
              </div>
              <MenuItem
                icon={<path d="M4 6h16v12H4zM4 7l8 6 8-6" />}
                title="Raise a support ticket"
                body="Tell us what's wrong or what you need"
                onClick={() => openTicket()}
              />
              <MenuItem
                icon={
                  <>
                    <circle cx="12" cy="12" r="9" />
                    <path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14M12 17h.01" />
                  </>
                }
                title="Help & FAQ"
                body="Answers to common questions"
                external
                onClick={() => {
                  setMenuOpen(false)
                  window.open(`${window.location.pathname}?page=support`, '_blank', 'noopener,noreferrer')
                }}
              />
              <MenuItem
                icon={
                  <>
                    <rect x="4" y="5" width="16" height="15" rx="2" />
                    <path d="M8 3v4M16 3v4M4 10h16" />
                  </>
                }
                title="Schedule a call"
                body="Talk to us about setup or your timetable"
                external={Boolean(BOOKING_URL)}
                onClick={scheduleCall}
              />
            </motion.div>
          )}
        </AnimatePresence>

        <button
          onClick={() => setMenuOpen((v) => !v)}
          aria-expanded={menuOpen}
          aria-label={menuOpen ? 'Close help menu' : 'Open help menu'}
          className="flex h-12 items-center gap-2 rounded-full bg-neutral-900 pl-4 pr-5 text-sm font-medium text-white shadow-lg shadow-black/20 transition-transform hover:scale-[1.03] hover:bg-neutral-800 active:scale-95"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            {menuOpen ? (
              <path d="M18 6 6 18M6 6l12 12" />
            ) : (
              <path d="M21 12a8 8 0 0 1-11.8 7L4 20l1-4.6A8 8 0 1 1 21 12Z" />
            )}
          </svg>
          {menuOpen ? 'Close' : 'Help'}
        </button>
      </div>

      <AnimatePresence>
        {form && <TicketModal initial={form} schoolId={schoolId} onClose={() => setForm(null)} />}
      </AnimatePresence>
    </>
  )
}

function MenuItem({ icon, title, body, onClick, external }) {
  return (
    <button
      role="menuitem"
      onClick={onClick}
      className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-slate-50"
    >
      <span className="mt-0.5 flex h-8 w-8 flex-none items-center justify-center rounded-lg bg-slate-100 text-slate-700">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          {icon}
        </svg>
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1 text-sm font-medium text-slate-800">
          {title}
          {external && (
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-slate-400">
              <path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
            </svg>
          )}
        </span>
        <span className="block text-xs text-slate-500">{body}</span>
      </span>
    </button>
  )
}

function TicketModal({ initial, schoolId, onClose }) {
  const [category, setCategory] = useState(initial.category)
  const [subject, setSubject] = useState(initial.subject)
  const [message, setMessage] = useState(initial.message)
  const [state, setState] = useState('editing') // editing | sending | sent
  const [error, setError] = useState(null)
  const [touched, setTouched] = useState(false)

  useEffect(() => {
    function onKey(e) {
      if (e.key === 'Escape' && state !== 'sending') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose, state])

  const missing = !subject.trim() || !message.trim()

  async function submit(e) {
    e.preventDefault()
    setTouched(true)
    if (missing) return
    setState('sending')
    setError(null)
    try {
      await api.createSupportTicket({
        category,
        subject: subject.trim(),
        message: message.trim(),
        school_id: schoolId ?? null,
      })
      setState('sent')
    } catch (err) {
      setError(err.message || `Couldn't send right now. Please email ${SUPPORT_EMAIL}.`)
      setState('editing')
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.15 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
      onMouseDown={(e) => e.target === e.currentTarget && state !== 'sending' && onClose()}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.97, y: 6 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.97, y: 6 }}
        transition={{ duration: 0.15, ease: 'easeOut' }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="ticket-title"
        className="w-full max-w-lg rounded-xl border border-slate-200 bg-white p-6 shadow-xl"
      >
        {state === 'sent' ? (
          <div className="flex flex-col items-start gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-full bg-neutral-900 text-white">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M20 6 9 17l-5-5" />
              </svg>
            </span>
            <h2 id="ticket-title" className="text-lg font-semibold">Ticket sent</h2>
            <p className="text-sm text-slate-500">
              We've got it and will reply to your email, usually within one working day.
            </p>
            <button
              onClick={onClose}
              className="mt-2 rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700"
            >
              Done
            </button>
          </div>
        ) : (
          <form onSubmit={submit} noValidate>
            <h2 id="ticket-title" className="text-lg font-semibold">Raise a support ticket</h2>
            <p className="mt-1 text-sm text-slate-500">We'll reply to the email you signed in with.</p>

            <label htmlFor="ticket-category" className="mb-1 mt-5 block text-xs font-medium text-slate-500">
              What's this about?
            </label>
            <select
              id="ticket-category"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:border-neutral-900 focus:outline-none"
            >
              {CATEGORIES.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </select>

            <label htmlFor="ticket-subject" className="mb-1 mt-4 block text-xs font-medium text-slate-500">
              Subject
            </label>
            <input
              id="ticket-subject"
              autoFocus={!initial.subject}
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              maxLength={150}
              placeholder="Timetable won't generate for Grade 8"
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-neutral-900 focus:outline-none"
            />

            <label htmlFor="ticket-message" className="mb-1 mt-4 block text-xs font-medium text-slate-500">
              Details
            </label>
            <textarea
              id="ticket-message"
              autoFocus={Boolean(initial.subject)}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              maxLength={5000}
              rows={6}
              placeholder="What were you trying to do, and what happened instead?"
              className="w-full resize-y rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-neutral-900 focus:outline-none"
            />

            {touched && missing && (
              <p className="mt-2 text-xs text-red-600">Add a subject and some details first.</p>
            )}
            {error && <p className="mt-2 text-xs text-red-600">{error}</p>}

            <div className="mt-5 flex items-center justify-between gap-3">
              <a href={`mailto:${SUPPORT_EMAIL}`} className="text-xs text-slate-400 hover:text-slate-600">
                Or email {SUPPORT_EMAIL}
              </a>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={onClose}
                  disabled={state === 'sending'}
                  className="rounded-md px-3 py-2 text-sm font-medium text-slate-500 hover:bg-slate-100"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={state === 'sending'}
                  className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
                >
                  {state === 'sending' ? 'Sending…' : 'Send ticket'}
                </button>
              </div>
            </div>
          </form>
        )}
      </motion.div>
    </motion.div>
  )
}
