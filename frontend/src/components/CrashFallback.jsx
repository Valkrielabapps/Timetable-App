/**
 * Shown instead of a blank page when a render error escapes React.
 *
 * Wired up as the ErrorBoundary fallback in main.jsx. Without a boundary,
 * any uncaught render error unmounts the whole tree and leaves the user
 * staring at white with no indication anything went wrong - and, since it
 * never reaches the network, no trace of it anywhere either.
 *
 * `resetError` comes from Sentry's ErrorBoundary and re-mounts the subtree,
 * which is worth offering before a full reload: it keeps whatever state lives
 * above the boundary and is instant when the error was transient.
 */
export default function CrashFallback({ resetError }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 p-6">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
        <h1 className="text-lg font-semibold text-slate-900">
          Something went wrong
        </h1>
        <p className="mt-2 text-sm text-slate-600">
          The page hit an unexpected error. Your saved data is safe - reloading
          usually clears it.
        </p>
        <div className="mt-6 flex justify-center gap-3">
          <button
            onClick={resetError}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50"
          >
            Try again
          </button>
          <button
            onClick={() => window.location.reload()}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-700"
          >
            Reload page
          </button>
        </div>
      </div>
    </div>
  )
}
