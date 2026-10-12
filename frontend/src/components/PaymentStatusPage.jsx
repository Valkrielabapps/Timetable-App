import { useEffect, useRef, useState } from 'react'
import { api, getToken } from '../api'
import { formatDate } from './BillingSection'

const POLL_MS = 3000
const MAX_POLLS = 20 // about a minute, then we stop and say it's still processing

/**
 * The return_url Cashfree sends the customer to after checkout:
 * /?page=payment-status&order_id=...
 *
 * Arriving here proves nothing - anyone can type this URL. The page asks the
 * backend, which asks Cashfree (Get Order API) and only reports PAID when
 * Cashfree does. While the order is still pending it polls for about a
 * minute, since a UPI or netbanking payment can take a few seconds to settle.
 */
export default function PaymentStatusPage({ orderId, onDone }) {
  const [state, setState] = useState({ kind: 'loading' })
  const polls = useRef(0)

  useEffect(() => {
    if (!orderId) {
      setState({ kind: 'error', message: 'This link is missing its order reference.' })
      return undefined
    }
    if (!getToken()) {
      setState({ kind: 'signin' })
      return undefined
    }
    let cancelled = false
    let timer = null

    async function check() {
      try {
        const order = await api.getPaymentOrder(orderId)
        if (cancelled) return
        if (order.status === 'PENDING') {
          polls.current += 1
          if (polls.current >= MAX_POLLS) {
            setState({ kind: 'slow', order })
            return
          }
          setState({ kind: 'pending', order })
          timer = setTimeout(check, POLL_MS)
          return
        }
        setState({ kind: order.status === 'PAID' ? 'paid' : 'failed', order })
      } catch (err) {
        if (cancelled) return
        setState({ kind: 'error', message: err.message || 'Could not check this payment.' })
      }
    }
    check()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [orderId])

  const { kind, order, message } = state
  const amount = order ? `₹${Number(order.amount).toLocaleString('en-IN')}` : ''

  const content = {
    loading: { title: 'Checking your payment…', body: 'This only takes a moment.', tone: 'neutral' },
    pending: {
      title: 'Payment processing',
      body: 'We are waiting for confirmation from the bank. Please keep this page open.',
      tone: 'neutral',
    },
    slow: {
      title: 'Still processing',
      body: "Your bank hasn't confirmed this payment yet. You can close this page: if the payment goes through, your plan is upgraded automatically within a few minutes, and if it doesn't, any money taken is refunded by your bank.",
      tone: 'neutral',
    },
    paid: {
      title: 'Payment successful',
      body: `Thank you. ${amount} received and your school is now on Pro${
        order?.plan_valid_until ? ` until ${formatDate(order.plan_valid_until)}` : ''
      }.`,
      tone: 'good',
    },
    failed: {
      title: order?.status === 'EXPIRED' ? 'Payment session expired' : 'Payment not completed',
      body: 'No money has been taken for this order. You can try again from Settings > Plan & billing.',
      tone: 'bad',
    },
    signin: { title: 'Sign in to see your payment', body: 'Your payment is safe either way. Sign in to check its status.', tone: 'neutral' },
    error: { title: "We couldn't check this payment", body: message, tone: 'bad' },
  }[kind]

  const iconTone = { good: 'bg-emerald-50 text-emerald-700', bad: 'bg-red-50 text-red-600', neutral: 'bg-slate-100 text-slate-600' }[content.tone]
  const spinning = kind === 'loading' || kind === 'pending'

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 p-6 text-slate-900">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
        <div className={`mx-auto flex h-12 w-12 items-center justify-center rounded-full ${iconTone}`} aria-hidden="true">
          {spinning ? (
            <span className="h-5 w-5 animate-spin rounded-full border-2 border-current border-t-transparent" />
          ) : content.tone === 'good' ? (
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
          ) : content.tone === 'bad' ? (
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M7 7l10 10M17 7L7 17" /></svg>
          ) : (
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>
          )}
        </div>
        <h1 className="mt-5 text-xl font-semibold" role="status">{content.title}</h1>
        <p className="mt-2 text-sm leading-relaxed text-slate-600">{content.body}</p>
        {orderId && <p className="mt-4 text-xs text-slate-400">Order reference: {orderId}</p>}
        <button
          onClick={onDone}
          className="mt-6 rounded-md bg-neutral-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-neutral-700"
        >
          {kind === 'signin' ? 'Sign in' : 'Back to Timetablz'}
        </button>
        {(kind === 'failed' || kind === 'error' || kind === 'slow') && (
          <p className="mt-4 text-xs text-slate-400">
            Questions? Write to <a className="underline" href="mailto:support@timetablz.com">support@timetablz.com</a> with the order reference.
          </p>
        )}
      </div>
    </div>
  )
}
