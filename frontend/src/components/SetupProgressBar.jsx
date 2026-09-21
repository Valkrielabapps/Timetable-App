/**
 * Compact, always-visible progress indicator for the header — shown on
 * every tab, not just Overview, since the actual setup work happens on
 * Data Entry and Constraints and a new admin shouldn't have to keep
 * clicking back to Overview just to see how close they are. Clicking it
 * jumps straight to the current step via `onNavigate(tab, subView)`.
 *
 * Purely presentational — App.jsx owns the single `useSetupProgress`
 * call (it also needs `allRequiredDone` to mute the Constraints/
 * Timetable tabs) and passes the result down, rather than this component
 * fetching the same data a second time.
 *
 * Collapses to a quiet "Ready" badge once every required step is done,
 * rather than permanently occupying header space nagging an admin who's
 * already generated a timetable and is just doing routine edits.
 */
export default function SetupProgressBar({ progress, onNavigate }) {
  const { requiredSteps, doneRequiredCount, currentStep, allRequiredDone, loaded } = progress

  if (!loaded) return null

  if (allRequiredDone) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700">
        <span aria-hidden="true">✓</span> Ready
      </span>
    )
  }

  return (
    <button
      type="button"
      onClick={() => currentStep && onNavigate(currentStep.tab, currentStep.subView)}
      title={currentStep ? `Next: ${currentStep.title}` : undefined}
      className="group flex items-center gap-2 rounded-md px-1.5 py-1 hover:bg-slate-50"
    >
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-slate-200">
        <div
          className="h-full rounded-full bg-neutral-900 transition-all"
          style={{ width: `${(doneRequiredCount / requiredSteps.length) * 100}%` }}
        />
      </div>
      <span className="whitespace-nowrap text-xs font-medium text-slate-500 group-hover:text-slate-700">
        {doneRequiredCount}/{requiredSteps.length} set up
      </span>
    </button>
  )
}
