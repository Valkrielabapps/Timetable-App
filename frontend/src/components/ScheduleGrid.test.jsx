import React from 'react'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ScheduleGrid from './ScheduleGrid'

/**
 * One week's grid, now rendered once per section and stacked.
 *
 * Extracted from TimetableTab for exactly that reason: repeating it inline
 * would have meant two copies of the drag, lock and violation handling, and
 * those would not have stayed identical for long. These tests cover the parts
 * that were previously only exercised through the whole tab.
 */

const PERIODS = {
  '0-0': { id: 1, day_of_week: 0, order: 0 },
  '0-1': { id: 2, day_of_week: 0, order: 1 },
}

const ENTRY = {
  id: 11, class_group_id: 100, subject_name: 'Hindi', teacher_name: 'Mrs. Rao',
  assistant_teacher_name: null, room_name: null, locked: false, lab_batch: null,
  period_id: 1, day_of_week: 0, order: 0,
}

function renderGrid(overrides = {}) {
  const props = {
    days: [0],
    orders: [0, 1],
    periodAt: (d, o) => PERIODS[`${d}-${o}`] ?? null,
    entriesAt: (d, o) => (d === 0 && o === 0 ? [ENTRY] : []),
    editable: true,
    violatingEntries: new Map(),
    onDragStart: vi.fn(),
    onDragEnd: vi.fn(),
    onDrop: vi.fn(),
    onToggleLock: vi.fn(),
    secondaryLine: (e) => e.teacher_name,
    showAssistant: true,
    ...overrides,
  }
  render(<ScheduleGrid {...props} />)
  return props
}

describe('ScheduleGrid', () => {
  it('labels rows from one even though periods are stored from zero', () => {
    renderGrid()
    // The database numbers periods from zero and every layer a person sees is
    // 1-based. Getting this wrong once already produced a timetable that broke
    // its own constraint.
    expect(screen.getByText('Period 1')).toBeInTheDocument()
    expect(screen.getByText('Period 2')).toBeInTheDocument()
  })

  it('shows the subject and whatever the caller chose as the second line', () => {
    renderGrid()
    expect(screen.getByText('Hindi')).toBeInTheDocument()
    expect(screen.getByText('Mrs. Rao')).toBeInTheDocument()
  })

  it('lets the caller decide what the second line says', () => {
    // Section view names the teacher; teacher view names the section. The grid
    // holds no opinion about which view it is serving.
    renderGrid({ secondaryLine: () => 'Sec B' })
    expect(screen.getByText('Sec B')).toBeInTheDocument()
    expect(screen.queryByText('Mrs. Rao')).not.toBeInTheDocument()
  })

  it('marks a slot that breaks a rule, and names the rule on hover', () => {
    const violation = { description: 'No class has Hindi in period 1.' }
    renderGrid({ violatingEntries: new Map([[11, [violation]]]) })
    const cell = screen.getByText('Hindi').closest('td')
    expect(cell.className).toContain('ring-amber-400')
    expect(cell).toHaveAttribute('title', violation.description)
  })

  it('leaves untouched slots unmarked', () => {
    renderGrid()
    expect(screen.getByText('Hindi').closest('td').className).not.toContain('ring-amber')
  })

  it('reports which entry started a drag, so the drop can be scoped', () => {
    // With every section on screen, a drop can land in a grid the slot does
    // not belong to. The caller needs the entry to tell.
    const props = renderGrid()
    fireEvent.dragStart(screen.getByText('Hindi').closest('[draggable]'))
    expect(props.onDragStart).toHaveBeenCalledWith(ENTRY)
  })

  it('does not let a locked slot be dragged', () => {
    // Locked means "keep this exactly here through the next regeneration", so
    // dragging it would contradict the thing the lock was for.
    renderGrid({ entriesAt: (d, o) => (d === 0 && o === 0 ? [{ ...ENTRY, locked: true }] : []) })
    expect(screen.getByText('Hindi').closest('[draggable]')).toHaveAttribute('draggable', 'false')
  })

  it('does let an unlocked slot be dragged', () => {
    renderGrid()
    expect(screen.getByText('Hindi').closest('[draggable]')).toHaveAttribute('draggable', 'true')
  })

  it('does not offer dragging or locking when it is not editable', () => {
    const props = renderGrid({ editable: false })
    fireEvent.click(screen.getByText('Hindi'))
    expect(props.onToggleLock).not.toHaveBeenCalled()
  })

  it('shows every batch of a split lab in one cell', () => {
    const batched = [
      { ...ENTRY, id: 21, lab_batch: 2, subject_name: 'Computer Science' },
      { ...ENTRY, id: 20, lab_batch: 1, subject_name: 'Computer Science' },
    ]
    renderGrid({ entriesAt: (d, o) => (d === 0 && o === 0 ? batched : []) })
    const cell = screen.getAllByText('Computer Science')[0].closest('td')
    // Sorted by batch, so they don't reorder between renders.
    expect(within(cell).getByText('Batch 1')).toBeInTheDocument()
    expect(within(cell).getByText('Batch 2')).toBeInTheDocument()
  })

  it('does not offer to drag a split lab slot', () => {
    // Editing one batch out of several needs an interaction nobody has
    // designed, and the solver does not honour locks on batched subjects.
    const batched = [
      { ...ENTRY, id: 20, lab_batch: 1 },
      { ...ENTRY, id: 21, lab_batch: 2 },
    ]
    const props = renderGrid({ entriesAt: (d, o) => (d === 0 && o === 0 ? batched : []) })
    const cell = screen.getAllByText('Hindi')[0].closest('td')
    fireEvent.drop(cell)
    expect(props.onDrop).not.toHaveBeenCalled()
  })

  it('says a slot is free rather than leaving the cell blank', () => {
    renderGrid()
    expect(screen.getByText('Free')).toBeInTheDocument()
  })
})
