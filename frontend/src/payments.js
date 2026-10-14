import { load } from '@cashfreepayments/cashfree-js'
import { api } from './api'

/**
 * Cashfree hosted checkout (https://www.cashfree.com/docs/payments/online/web/redirect).
 *
 * The backend creates the order and returns only a payment_session_id; this
 * opens Cashfree's page with it. Nothing here decides whether a payment
 * succeeded - the payment status page asks the backend, which asks Cashfree.
 *
 * Mode and redirect target come from Vite env vars and default to the safe
 * choices: sandbox, and a same-tab redirect.
 */
export const CASHFREE_MODE = import.meta.env.VITE_CASHFREE_MODE === 'production' ? 'production' : 'sandbox'
export const REDIRECT_TARGET = import.meta.env.VITE_CASHFREE_REDIRECT_TARGET === '_modal' ? '_modal' : '_self'

export function paymentStatusUrl(orderId) {
  return `${window.location.pathname}?page=payment-status&order_id=${encodeURIComponent(orderId)}`
}

let sdkPromise = null
function cashfreeSdk() {
  // Loaded once, on first use, so the SDK script isn't fetched for visitors
  // who never pay.
  if (!sdkPromise) {
    sdkPromise = load({ mode: CASHFREE_MODE }).catch((err) => {
      sdkPromise = null
      throw err
    })
  }
  return sdkPromise
}

/**
 * Create an order for `plan` and open checkout.
 *
 * With `_self` the browser leaves the app; Cashfree brings it back to the
 * return URL the backend set (?page=payment-status&order_id=...).
 * With `_modal` the promise resolves when the popup closes, and whatever it
 * reports, we go to the same status page so the backend confirms it.
 */
export async function startCheckout({ schoolId, phone, plan = 'pro', offerId = null }) {
  const { order_id: orderId, payment_session_id: paymentSessionId } = await api.createPaymentOrder({
    school_id: schoolId,
    phone,
    plan,
    // A custom offer made for this school: the server takes the price,
    // length and limits from the offer.
    ...(offerId != null ? { offer_id: offerId } : {}),
  })

  const cashfree = await cashfreeSdk()
  if (!cashfree) throw new Error('The payment page could not be loaded. Please try again.')

  const result = await cashfree.checkout({ paymentSessionId, redirectTarget: REDIRECT_TARGET })

  if (REDIRECT_TARGET === '_modal') {
    // result.redirect: Cashfree will redirect to the return URL itself
    // (in-app browsers); nothing to do. result.error (popup closed or
    // failed) and result.paymentDetails (finished, any outcome): ask the
    // backend what actually happened.
    if (result?.redirect) return { orderId, redirected: true }
    window.location.assign(paymentStatusUrl(orderId))
  }
  return { orderId }
}
