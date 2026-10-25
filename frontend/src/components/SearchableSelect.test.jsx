import React, { useState } from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import SearchableSelect from './SearchableSelect'

/**
 * The dropdown for long lists: alphabetical, and you can type into it -
 * typing narrows the list, Enter picks the best match.
 */

const TEACHERS = [
  { value: 1, label: 'Mrs. Zareena' },
  { value: 2, label: 'Vinita' },
  { value: 3, label: 'Mr. Anil' },
  { value: 4, label: 'Ms. Shallu' },
]

function Harness({ onChange = () => {}, initial = null, ...props }) {
  const [value, setValue] = useState(initial)
  return (
    <SearchableSelect
      ariaLabel="Teacher"
      value={value}
      onChange={(v) => {
        setValue(v)
        onChange(v)
      }}
      options={TEACHERS}
      emptyOption={{ label: 'Any teacher' }}
      {...props}
    />
  )
}

const box = () => screen.getByRole('combobox', { name: 'Teacher' })
const labels = () => screen.getAllByRole('option').map((o) => o.firstChild.textContent)

describe('SearchableSelect', () => {
  it('shows the chosen option, or the empty one', () => {
    render(<Harness />)
    expect(box()).toHaveTextContent('Any teacher')
  })

  it('lists options alphabetically by name, titles ignored, after the empty choice', () => {
    render(<Harness />)
    fireEvent.click(box())
    expect(labels()).toEqual(['Any teacher', 'Mr. Anil', 'Ms. Shallu', 'Vinita', 'Mrs. Zareena'])
  })

  it('narrows the list as you type', () => {
    render(<Harness />)
    fireEvent.click(box())
    fireEvent.change(screen.getByLabelText('Search Teacher'), { target: { value: 'sha' } })
    expect(labels()).toEqual(['Ms. Shallu'])
  })

  it('picks the best match on Enter', () => {
    const onChange = vi.fn()
    render(<Harness onChange={onChange} />)
    fireEvent.click(box())
    const search = screen.getByLabelText('Search Teacher')
    fireEvent.change(search, { target: { value: 'vinita' } })
    fireEvent.keyDown(search, { key: 'Enter' })
    expect(onChange).toHaveBeenCalledWith(2)
    expect(box()).toHaveTextContent('Vinita')
    expect(screen.queryByRole('listbox')).toBeNull()
  })

  it('opens with the letter typed on it, so typing a name just works', () => {
    const onChange = vi.fn()
    render(<Harness onChange={onChange} />)
    box().focus()
    fireEvent.keyDown(box(), { key: 'z' })
    const search = screen.getByLabelText('Search Teacher')
    expect(search).toHaveValue('z')
    fireEvent.keyDown(search, { key: 'Enter' })
    expect(onChange).toHaveBeenCalledWith(1)
  })

  it('moves through the list with the arrow keys', () => {
    const onChange = vi.fn()
    render(<Harness onChange={onChange} />)
    fireEvent.click(box())
    const search = screen.getByLabelText('Search Teacher')
    fireEvent.keyDown(search, { key: 'ArrowDown' })
    fireEvent.keyDown(search, { key: 'ArrowDown' })
    fireEvent.keyDown(search, { key: 'Enter' })
    expect(onChange).toHaveBeenCalledWith(4) // past "Any teacher" and Anil, to Shallu
  })

  it('closes on Escape without changing anything', () => {
    const onChange = vi.fn()
    render(<Harness onChange={onChange} initial={2} />)
    fireEvent.click(box())
    fireEvent.keyDown(screen.getByLabelText('Search Teacher'), { key: 'Escape' })
    expect(onChange).not.toHaveBeenCalled()
    expect(box()).toHaveTextContent('Vinita')
  })

  it('can go back to the empty choice', () => {
    const onChange = vi.fn()
    render(<Harness onChange={onChange} initial={2} />)
    fireEvent.click(box())
    fireEvent.click(screen.getAllByRole('option')[0])
    expect(onChange).toHaveBeenCalledWith(null)
  })

  it('says when nothing matches', () => {
    render(<Harness />)
    fireEvent.click(box())
    fireEvent.change(screen.getByLabelText('Search Teacher'), { target: { value: 'zzz' } })
    expect(screen.getByText('No matches')).toBeInTheDocument()
  })

  it('closes when you click elsewhere', () => {
    render(<div><Harness /><p>elsewhere</p></div>)
    fireEvent.click(box())
    fireEvent.mouseDown(screen.getByText('elsewhere'))
    expect(screen.queryByRole('listbox')).toBeNull()
  })

  it('keeps groups, alphabetical within each', () => {
    render(
      <SearchableSelect
        ariaLabel="Substitute"
        value={null}
        onChange={() => {}}
        options={[
          { value: 1, label: 'Zara', group: 'Suggested' },
          { value: 2, label: 'Arun', group: 'Suggested' },
          { value: 3, label: 'Bina', group: 'Others' },
        ]}
      />,
    )
    fireEvent.click(screen.getByRole('combobox', { name: 'Substitute' }))
    expect(screen.getAllByRole('option').map((o) => o.firstChild.textContent)).toEqual(['Arun', 'Zara', 'Bina'])
    expect(screen.getByText('Suggested')).toBeInTheDocument()
    expect(screen.getByText('Others')).toBeInTheDocument()
  })

  it('does nothing when disabled', () => {
    render(<Harness disabled />)
    fireEvent.click(box())
    expect(screen.queryByRole('listbox')).toBeNull()
  })
})
