import { useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'

/**
 * A themed replacement for window.confirm.
 *
 *   if (!(await confirmDialog({ title: 'Remove this constraint?', message: '...' }))) return
 *
 * Resolves true on confirm, false on Cancel / Escape / clicking outside.
 * Rendered imperatively into its own root so callers don't need a provider
 * or local open/closed state - every former window.confirm call site becomes
 * a one-line change.
 *
 * Under Vitest it defers to window.confirm, so existing tests that stub
 * window.confirm keep working without having to drive a dialog.
 */
export function confirmDialog({
  title = 'Are you sure?',
  message = '',
  detail = '',
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  danger = false,
} = {}) {
  if (import.meta.env?.MODE === 'test') {
    return Promise.resolve(window.confirm([title, detail || message].filter(Boolean).join('\n\n')))
  }

  return new Promise((resolve) => {
    const host = document.createElement('div')
    document.body.appendChild(host)
    const root = createRoot(host)
    const previouslyFocused = document.activeElement

    function finish(value) {
      root.unmount()
      host.remove()
      if (previouslyFocused && typeof previouslyFocused.focus === 'function') previouslyFocused.focus()
      resolve(value)
    }

    root.render(
      <Dialog
        title={title}
        message={message}
        detail={detail}
        confirmLabel={confirmLabel}
        cancelLabel={cancelLabel}
        danger={danger}
        onDone={finish}
      />
    )
  })
}

function Dialog({ title, message, detail, confirmLabel, cancelLabel, danger, onDone }) {
  const [shown, setShown] = useState(false)
  const confirmRef = useRef(null)
  const closing = useRef(false)

  useEffect(() => {
    const raf = requestAnimationFrame(() => setShown(true))
    confirmRef.current?.focus()
    return () => cancelAnimationFrame(raf)
  }, [])

  function close(value) {
    if (closing.current) return
    closing.current = true
    setShown(false)
    setTimeout(() => onDone(value), 140)
  }

  useEffect(() => {
    function onKey(e) {
      if (e.key === 'Escape') {
        e.preventDefault()
        close(false)
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  })

  return (
    <div
      className={`fixed inset-0 z-[100] flex items-center justify-center p-4 transition-opacity duration-150 ${
        shown ? 'opacity-100' : 'opacity-0'
      }`}
    >
      <div className="absolute inset-0 bg-neutral-900/40" onMouseDown={() => close(false)} aria-hidden="true" />
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby={message || detail ? 'confirm-dialog-body' : undefined}
        className={`relative w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-xl transition-all duration-150 ${
          shown ? 'translate-y-0 scale-100' : 'translate-y-2 scale-[0.98]'
        }`}
      >
        <div className="flex items-start gap-4">
          <div
            className={`flex h-10 w-10 flex-none items-center justify-center rounded-full ${
              danger ? 'bg-red-50 text-red-600' : 'bg-slate-100 text-neutral-800'
            }`}
            aria-hidden="true"
          >
            {danger ? (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v6M14 11v6" />
              </svg>
            ) : (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="9" />
                <path d="M12 8v4M12 16h.01" />
              </svg>
            )}
          </div>
          <div className="min-w-0 flex-1">
            <h2 id="confirm-dialog-title" className="text-base font-semibold text-neutral-900">
              {title}
            </h2>
            <div id="confirm-dialog-body">
              {message && <p className="mt-1.5 text-sm leading-relaxed text-slate-600">{message}</p>}
              {detail && (
                <p className="mt-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800">
                  {detail}
                </p>
              )}
            </div>
          </div>
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <button
            onClick={() => close(false)}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            {cancelLabel}
          </button>
          <button
            ref={confirmRef}
            onClick={() => close(true)}
            className={`rounded-lg px-4 py-2 text-sm font-medium text-white ${
              danger ? 'bg-red-600 hover:bg-red-700' : 'bg-neutral-900 hover:bg-neutral-700'
            }`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
