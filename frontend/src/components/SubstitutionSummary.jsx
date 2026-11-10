import { useState } from 'react'
import { api } from '../api'
import { copyText, formatDate, groupRows, leaveText, printSummary, summaryText } from '../substitutionSummary'

/**
 * One day's cover, as it's sent round: the date and day, who is on leave
 * (all day, or which periods), then period by period who takes each of
 * their lessons - with lessons nobody could take marked "Not covered".
 * For the whole school the lessons are grouped by part of the school.
 *
 * Print, Download PDF and Copy for WhatsApp all carry exactly this.
 */
export default function SubstitutionSummary({ schoolId, schoolName, summary, readOnly = false }) {
  const [message, setMessage] = useState(null)
  const date = summary.date
  const category = summary.category

  const flash = (text) => {
    setMessage(text)
    setTimeout(() => setMessage(null), 2500)
  }

  const copy = async () => {
    flash((await copyText(summaryText(summary))) ? 'Copied - paste it into WhatsApp.' : 'Couldn’t copy. Try again.')
  }
  const print = () => {
    if (!printSummary(summary, schoolName)) flash('Allow pop-ups for this site to print.')
  }
  const pdf = async () => {
    try {
      await api.downloadSubstitutionSummaryPdf(schoolId, date, category)
    } catch (err) {
      flash(err.message)
    }
  }

  const [emailOpen, setEmailOpen] = useState(false)
  const [everyone, setEveryone] = useState(false)
  const [sending, setSending] = useState(false)
  const [emailed, setEmailed] = useState(null)
  const sendEmails = async () => {
    setSending(true)
    try {
      setEmailed(await api.notifySubstitutions(schoolId, { date, category, everyone }))
    } catch (err) {
      setEmailed({ error: err.message })
    } finally {
      setSending(false)
    }
  }

  return (
    <section aria-label="Substitution summary" className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="text-lg font-semibold text-gray-900">{formatDate(date)}</h3>
          <p className="text-sm text-gray-500">{summary.category_label}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={print} className="rounded border border-gray-300 px-3 py-1.5 text-sm font-medium hover:bg-gray-50">
            Print
          </button>
          <button onClick={pdf} className="rounded border border-gray-300 px-3 py-1.5 text-sm font-medium hover:bg-gray-50">
            Download PDF
          </button>
          <button onClick={copy} className="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700">
            Copy for WhatsApp
          </button>
          {!readOnly && summary.rows.some((r) => r.substitute) && (
            <button onClick={() => setEmailOpen(!emailOpen)} aria-expanded={emailOpen} className="rounded bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-neutral-700">
              Email teachers
            </button>
          )}
        </div>
      </div>
      {emailOpen && (
        <div className="mt-3 rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm">
          <p className="text-gray-700">
            Each covering teacher gets an email with their periods and a calendar invite, so the cover shows up in
            their Google Calendar. Emailing again after a change updates their calendar, and anyone no longer covering
            gets a cancellation.
          </p>
          <label className="mt-2 flex items-center gap-2 text-gray-700">
            <input type="checkbox" checked={everyone} onChange={(e) => setEveryone(e.target.checked)} />
            Also send the whole day&rsquo;s arrangement to every other teacher
          </label>
          <button onClick={sendEmails} disabled={sending} className="mt-2 rounded bg-neutral-900 px-3 py-1.5 font-medium text-white hover:bg-neutral-700 disabled:opacity-50">
            {sending ? 'Sending…' : 'Send emails'}
          </button>
          {emailed && (
            <div role="status" className="mt-2 space-y-1">
              {emailed.error ? (
                <p className="text-red-700">{emailed.error}</p>
              ) : !emailed.email_configured ? (
                <p className="text-amber-800">Email isn&rsquo;t set up on the server yet, so nothing was sent.</p>
              ) : (
                <>
                  <p className="text-emerald-800">
                    {emailed.sent.length > 0 ? `Sent to ${emailed.sent.join(', ')}.` : 'No covering teacher had an email to send to.'}
                    {emailed.cancelled > 0 && ` ${emailed.cancelled} cancelled cover${emailed.cancelled === 1 ? '' : 's'} removed from calendars.`}
                    {emailed.summary_sent > 0 && ` The day’s arrangement went to ${emailed.summary_sent} other teacher${emailed.summary_sent === 1 ? '' : 's'}.`}
                  </p>
                  {emailed.no_email.length > 0 && (
                    <p className="text-amber-800">No email address for {emailed.no_email.join(', ')}. Add one on the Teachers page.</p>
                  )}
                  {emailed.failed.length > 0 && <p className="text-red-700">Couldn&rsquo;t send to {emailed.failed.join(', ')}. Try again.</p>}
                </>
              )}
            </div>
          )}
        </div>
      )}
      {message && <p role="status" className="mt-2 text-sm text-gray-600">{message}</p>}

      <div className="mt-4 text-sm text-gray-800">
        <span className="font-semibold">On leave: </span>
        {summary.on_leave.length === 0 ? 'nobody recorded' : summary.on_leave.map(leaveText).join(', ')}
      </div>

      {summary.uncovered > 0 && (
        <p className="mt-3 rounded bg-red-50 px-3 py-2 text-sm font-medium text-red-700">
          {summary.uncovered} period{summary.uncovered === 1 ? '' : 's'} still need{summary.uncovered === 1 ? 's' : ''} cover.
        </p>
      )}

      {summary.rows.length === 0 ? (
        <p className="mt-4 text-sm text-gray-500">No lessons need cover.</p>
      ) : (
        groupRows(summary).map((group) => (
          <div key={group.label} className="mt-5">
            {category == null && <h4 className="mb-2 text-sm font-semibold text-gray-700">{group.label}</h4>}
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="bg-gray-100 text-left text-gray-600">
                    <th className="border border-gray-200 px-3 py-2 font-medium">Period</th>
                    <th className="border border-gray-200 px-3 py-2 font-medium">Class</th>
                    <th className="border border-gray-200 px-3 py-2 font-medium">Subject</th>
                    <th className="border border-gray-200 px-3 py-2 font-medium">On leave</th>
                    <th className="border border-gray-200 px-3 py-2 font-medium">Replaced by</th>
                  </tr>
                </thead>
                <tbody>
                  {group.rows.map((r, i) => (
                    <tr key={i} className={r.substitute ? '' : 'bg-red-50'}>
                      <td className="border border-gray-200 px-3 py-2">{r.period}</td>
                      <td className="border border-gray-200 px-3 py-2">{r.class_group}</td>
                      <td className="border border-gray-200 px-3 py-2">{r.subject}</td>
                      <td className="border border-gray-200 px-3 py-2">{r.absent_teacher}</td>
                      <td className="border border-gray-200 px-3 py-2">
                        {r.substitute ?? <span className="font-semibold text-red-700">Not covered</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))
      )}
    </section>
  )
}
