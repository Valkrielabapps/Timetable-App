/**
 * What one typed rule was understood to mean, shown before anything is saved.
 *
 * This is the only thing standing between a misread sentence and a wrong
 * timetable, which is worth being explicit about because it looks like a
 * politeness.
 *
 * Rules used to be matched against nine fixed types, and anything outside them
 * was saved as unenforced text — so a misreading announced itself by visibly
 * doing nothing. Rules are now expressed in a general representation that can
 * say far more, and the price is that almost any sentence yields a *valid*
 * rule. A misreading no longer fails; it schedules something nobody asked for,
 * faithfully, with nothing anywhere to show it. Reading against real rules,
 * about a third of the ones that parsed cleanly meant something other than
 * what was typed — and nearly every one of those was obvious on sight:
 *
 *     typed:  PE shouldn't be on two days in a row
 *     read:   PE periods and PE periods are never back to back
 *
 * Nobody confirms that. Which is the point: the person who wrote the sentence
 * is the only one who can tell, and they can only tell if they are shown it.
 *
 * So the sentence is the loudest thing here, the buttons are deliberately not
 * weighted towards accepting, and nothing is pre-confirmed.
 */
export default function ConstraintInterpretation({
  typed,
  interpretation,
  saving,
  onConfirm,
  onReword,
  onCancel,
}) {
  const { understood, sentence, unknown_names: unknownNames = [] } = interpretation
  const blocked = unknownNames.length > 0

  if (!understood) {
    return (
      <NotUnderstood typed={typed} interpretation={interpretation} onReword={onReword} onCancel={onCancel} />
    )
  }

  return (
    <div className="flex flex-col gap-3 rounded-md border border-slate-300 bg-slate-50 p-4">
      <div className="flex flex-col gap-1">
        <p className="text-xs uppercase tracking-wide text-slate-500">You typed</p>
        <p className="text-sm text-slate-600">{typed}</p>
      </div>

      <div className="flex flex-col gap-1">
        <p className="text-xs uppercase tracking-wide text-slate-500">
          This is what we understood
        </p>
        {/* Larger and darker than the input above it. Whatever else is on this
            panel, the sentence is the thing that has to be read. */}
        <p className="text-base font-medium leading-snug text-slate-900">{sentence}</p>
      </div>

      {blocked && (
        <p className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {/* Caught here rather than at generation time, where it would be a
              warning on a timetable that has already been built. */}
          This mentions {unknownNames.join(', ')}, which isn&apos;t in your school&apos;s data
          yet. Add {unknownNames.length === 1 ? 'it' : 'them'} on the Data tab, or reword the
          rule to use a name you already have.
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={saving || blocked}
          onClick={onConfirm}
          className="rounded-md bg-neutral-900 px-3.5 py-1.5 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
        >
          {saving ? 'Saving…' : "Yes, that's right"}
        </button>
        {/* Same visual weight as each other, and neither of them styled as the
            lesser option: "no" has to be as easy as "yes" or the check stops
            being a check. */}
        <button
          type="button"
          disabled={saving}
          onClick={onReword}
          className="rounded-md border border-slate-300 px-3.5 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50"
        >
          No — let me reword it
        </button>
        <button
          type="button"
          disabled={saving}
          onClick={onCancel}
          className="text-sm text-slate-500 underline underline-offset-2 hover:text-slate-700 disabled:opacity-50"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

/**
 * The parser declining, rather than guessing.
 *
 * Worth showing as prominently as a successful reading. A rule it refuses to
 * guess at is a rule that would otherwise have been wrong, so this is the
 * system working — but only if the admin is told what to do about it, which is
 * why the question and the alternative readings matter more than the reason
 * code does.
 */
function NotUnderstood({ typed, interpretation, onReword, onCancel }) {
  const { reason, explanation, question, readings = [] } = interpretation

  return (
    <div className="flex flex-col gap-3 rounded-md border border-amber-300 bg-amber-50 p-4">
      <div className="flex flex-col gap-1">
        <p className="text-xs uppercase tracking-wide text-amber-800">You typed</p>
        <p className="text-sm text-amber-900">{typed}</p>
      </div>

      <div className="flex flex-col gap-1.5">
        <p className="text-sm font-medium text-amber-900">{HEADINGS[reason] ?? HEADINGS.ambiguous}</p>
        <p className="text-sm text-amber-900">{explanation}</p>
        {question && <p className="text-sm font-medium text-amber-900">{question}</p>}
        {readings.length > 0 && (
          <ul className="ml-4 list-disc text-sm text-amber-900">
            {readings.map((reading) => (
              <li key={reading}>{reading}</li>
            ))}
          </ul>
        )}
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onReword}
          className="rounded-md bg-neutral-900 px-3.5 py-1.5 text-sm font-medium text-white hover:bg-neutral-700"
        >
          Reword it
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="text-sm text-amber-800 underline underline-offset-2 hover:text-amber-950"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

// Said in the admin's terms, not the parser's. "not_supported" in particular
// is not their fault and shouldn't read like it is — the rule is fine, the app
// can't do it yet.
const HEADINGS = {
  ambiguous: 'This could mean more than one thing',
  too_vague: "There's nothing specific enough to schedule on",
  unknown_reference: "That name isn't in your school's data",
  not_a_rule: "That doesn't look like a scheduling rule",
  contradictory: "This can't hold alongside itself",
  not_supported: "We can't handle this kind of rule yet",
}
