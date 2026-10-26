import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SubstitutionSummary from './SubstitutionSummary'
import { formatDate, groupRows, summaryHtml, summaryText, weekdayOf } from '../substitutionSummary'

const api = vi.hoisted(() => ({ downloadSubstitutionSummaryPdf: vi.fn() }))
vi.mock('../api', () => ({ api }))

const row = (period, cls, category, label, absent, sub) => ({
  period, class_group: cls, subject: 'Maths', category, category_label: label, absent_teacher: absent, substitute: sub,
})
const WHOLE = {
  date: '2026-10-26', weekday: 'Monday', category: null, category_label: 'Whole school',
  on_leave: [
    { teacher_id: 11, teacher: 'Mr. Khan', periods: ['Period 2', 'Period 6'] },
    { teacher_id: 10, teacher: 'Mrs. Rao', periods: null },
  ],
  rows: [
    row('Period 1', 'Grade 7 - A', 'middle', 'Middle', 'Mr. Khan', 'Ms. Iyer'),
    row('Period 2', 'Grade 3 - A', 'primary', 'Primary', 'Mrs. Rao', null),
    row('Period 3', 'Foundation - A', null, 'Other', 'Mrs. Rao', 'Dr. Sen'),
  ],
  uncovered: 1,
}

afterEach(() => vi.restoreAllMocks())

describe('dates', () => {
  it('reads the date as a local day, with the app’s Monday-first weekday', () => {
    expect(formatDate('2026-10-26')).toBe('Monday, 26 October 2026')
    expect(formatDate('2026-11-01')).toBe('Sunday, 1 November 2026')
    expect(weekdayOf('2026-10-26')).toBe(0)
    expect(weekdayOf('2026-11-01')).toBe(6)
  })
})

describe('the summary as text', () => {
  it('groups the whole school by part, in the usual order, unplaced grades last', () => {
    expect(groupRows(WHOLE).map((g) => [g.label, g.rows.map((r) => r.period)])).toEqual([
      ['Primary', ['Period 2']], ['Middle', ['Period 1']], ['Other', ['Period 3']],
    ])
    const primary = { ...WHOLE, category: 'primary', category_label: 'Primary', rows: [WHOLE.rows[1]] }
    expect(groupRows(primary).map((g) => g.label)).toEqual(['Primary'])
  })

  it('is a WhatsApp message with the day, who is away and each lesson', () => {
    expect(summaryText(WHOLE)).toBe([
      '*Substitutions — Monday, 26 October 2026*',
      'Whole school',
      '',
      '*On leave:* Mr. Khan (Period 2, Period 6), Mrs. Rao (whole day)',
      '',
      '*Primary*',
      'Period 2 · Grade 3 - A · Maths: Mrs. Rao → *NOT COVERED*',
      '',
      '*Middle*',
      'Period 1 · Grade 7 - A · Maths: Mr. Khan → Ms. Iyer',
      '',
      '*Other*',
      'Period 3 · Foundation - A · Maths: Mrs. Rao → Dr. Sen',
      '',
      '⚠️ 1 period still needs cover.',
    ].join('\n'))
  })

  it('for one part, no part headings; with nothing to cover, says so', () => {
    const text = summaryText({ ...WHOLE, category: 'primary', category_label: 'Primary', rows: [], on_leave: [], uncovered: 0 })
    expect(text).toBe('*Substitutions — Monday, 26 October 2026*\nPrimary\n\nNo lessons need cover.')
  })

  it('the printed page escapes names', () => {
    const html = summaryHtml({ ...WHOLE, rows: [row('Period 1', 'Grade 3 - A', 'primary', 'Primary', '<b>X</b>', null)] }, 'A & B')
    expect(html).toContain('&lt;b&gt;X&lt;/b&gt;')
    expect(html).toContain('A &amp; B · Whole school')
    expect(html).toContain('Not covered')
  })
})

describe('the summary on screen', () => {
  it('shows the day, who is away, and each part’s lessons with uncovered ones marked', () => {
    render(<SubstitutionSummary schoolId={1} summary={WHOLE} />)
    expect(screen.getByText('Monday, 26 October 2026')).toBeInTheDocument()
    expect(screen.getByText('Mr. Khan (Period 2, Period 6), Mrs. Rao (whole day)')).toBeInTheDocument()
    expect(screen.getAllByRole('heading', { level: 4 }).map((h) => h.textContent)).toEqual(['Primary', 'Middle', 'Other'])
    const uncovered = screen.getByText('Not covered').closest('tr')
    expect(within(uncovered).getByText('Mrs. Rao')).toBeInTheDocument()
    expect(uncovered.className).toContain('bg-red-50')
    expect(screen.getByText('1 period still needs cover.')).toBeInTheDocument()
  })

  it('copies the message for WhatsApp', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    render(<SubstitutionSummary schoolId={1} summary={WHOLE} />)
    fireEvent.click(screen.getByText('Copy for WhatsApp'))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(summaryText(WHOLE)))
    expect(await screen.findByRole('status')).toHaveTextContent('Copied')
  })

  it('downloads the PDF for this date and part', () => {
    render(<SubstitutionSummary schoolId={1} summary={{ ...WHOLE, category: 'middle' }} />)
    fireEvent.click(screen.getByText('Download PDF'))
    expect(api.downloadSubstitutionSummaryPdf).toHaveBeenCalledWith(1, '2026-10-26', 'middle')
  })

  it('prints a page with just the summary', () => {
    const doc = { write: vi.fn(), close: vi.fn() }
    const win = { document: doc, focus: vi.fn(), print: vi.fn() }
    vi.spyOn(window, 'open').mockReturnValue(win)
    render(<SubstitutionSummary schoolId={1} schoolName="Greenfield" summary={WHOLE} />)
    fireEvent.click(screen.getByText('Print'))
    expect(doc.write).toHaveBeenCalledWith(summaryHtml(WHOLE, 'Greenfield'))
    expect(win.print).toHaveBeenCalled()
  })

  it('says so when the print window is blocked', async () => {
    vi.spyOn(window, 'open').mockReturnValue(null)
    render(<SubstitutionSummary schoolId={1} summary={WHOLE} />)
    fireEvent.click(screen.getByText('Print'))
    expect(await screen.findByRole('status')).toHaveTextContent('Allow pop-ups')
  })
})
