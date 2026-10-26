import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import GradeCategoriesSection from './GradeCategoriesSection'
import { optionsOf, pick } from '../test/pick'

const api = vi.hoisted(() => ({ getGradeCategories: vi.fn(), saveGradeCategories: vi.fn() }))
vi.mock('../api', () => ({ api }))

const GRADES = [
  { grade: 'LKG', category: 'pre_primary', default: 'pre_primary' },
  { grade: 'Grade 6', category: 'middle', default: 'middle' },
  { grade: 'Foundation', category: null, default: null },
]
const shown = (grade) =>
  screen.getByRole('combobox', { name: `Part of the school for ${grade}` }).textContent.replace('▾', '').trim()

beforeEach(() => {
  vi.clearAllMocks()
  api.getGradeCategories.mockResolvedValue(GRADES)
})

describe('Settings > School categories', () => {
  it('shows each grade’s part, the parts in the school’s order', async () => {
    render(<GradeCategoriesSection schoolId={1} isAdmin />)
    await screen.findByText('LKG')
    expect(shown('LKG')).toBe('Pre-primary')
    expect(shown('Grade 6')).toBe('Middle')
    expect(shown('Foundation')).toBe('None')
    expect(optionsOf('Part of the school for Grade 6')).toEqual(['None', 'Pre-primary', 'Primary', 'Middle', 'High school'])
  })

  it('saves a change, showing the default beside it', async () => {
    api.saveGradeCategories.mockResolvedValue([
      GRADES[0], { grade: 'Grade 6', category: 'primary', default: 'middle' }, GRADES[2],
    ])
    render(<GradeCategoriesSection schoolId={1} isAdmin />)
    await screen.findByText('LKG')
    expect(screen.getByText('Save')).toBeDisabled()
    pick('Part of the school for Grade 6', 'Primary')
    expect(screen.getByText('Default: Middle')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Save'))
    await waitFor(() => expect(api.saveGradeCategories).toHaveBeenCalledWith(1, {
      LKG: 'pre_primary', 'Grade 6': 'primary', Foundation: null,
    }))
    expect(await screen.findByRole('status')).toHaveTextContent('Saved')
    expect(screen.getByText('Save')).toBeDisabled()
  })

  it('a viewer sees the parts but can’t change them', async () => {
    render(<GradeCategoriesSection schoolId={1} isAdmin={false} />)
    await screen.findByText('LKG')
    expect(screen.getByRole('combobox', { name: 'Part of the school for LKG' })).toBeDisabled()
    expect(screen.queryByText('Save')).not.toBeInTheDocument()
  })
})
