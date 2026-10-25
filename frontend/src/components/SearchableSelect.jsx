import { useEffect, useMemo, useRef, useState } from 'react'
import { compareNames, rankMatches } from '../sorting'

/**
 * A dropdown you can type into - for the long lists, teachers and subjects.
 *
 * A plain <select> already jumps to an option when you type its first
 * letter, but it doesn't narrow the list, it forgets what you typed if you
 * pause, and browsers disagree about the details. Here, with the dropdown
 * focused, typing opens it and narrows it as you go: "vin" leaves Vinita,
 * and Enter picks the best match. Arrow keys move, Escape closes.
 *
 * Options are alphabetical by default, titles ignored - see src/sorting.js.
 * Options can carry a `group` (shown as headings, in the order the groups
 * first appear) and a `hint` (shown faintly beside the label).
 *
 *   options      [{ value, label, group?, hint? }]
 *   emptyOption  { label } for a "none"/"any" choice, whose value is null
 */
export default function SearchableSelect({
  value,
  onChange,
  options,
  emptyOption = null,
  ariaLabel,
  id,
  disabled = false,
  placeholder = 'Select…',
  className = '',
  sort = true,
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [highlight, setHighlight] = useState(0)
  const root = useRef(null)
  const button = useRef(null)

  const selected = options.find((o) => value != null && String(o.value) === String(value))
  const shownLabel = selected?.label ?? (value == null || value === '' ? emptyOption?.label : null) ?? placeholder

  // What the open list shows: everything (alphabetical within its group), or
  // the matches for what has been typed, best first.
  const list = useMemo(() => {
    if (query.trim()) return rankMatches(options, query, (o) => o.label)
    const ordered = sort ? [...options].sort((a, b) => compareNames(a.label, b.label)) : options
    const groups = [...new Set(options.map((o) => o.group ?? ''))]
    const grouped = groups.flatMap((g) => ordered.filter((o) => (o.group ?? '') === g))
    return emptyOption ? [{ value: null, label: emptyOption.label, empty: true }, ...grouped] : grouped
  }, [options, query, sort, emptyOption])

  useEffect(() => {
    if (!open) return undefined
    const close = (e) => {
      if (root.current && !root.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  function openWith(text) {
    if (disabled) return
    setQuery(text)
    // Opening without typing starts on whatever is chosen now.
    const at = text ? 0 : Math.max(0, list.findIndex((o) => String(o.value) === String(value)))
    setHighlight(at)
    setOpen(true)
  }

  function choose(option) {
    setOpen(false)
    setQuery('')
    button.current?.focus()
    if (option) onChange(option.value)
  }

  function onButtonKey(e) {
    if (disabled) return
    if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey && e.key !== ' ') {
      e.preventDefault()
      openWith(e.key)
    } else if (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      openWith('')
    }
  }

  function onSearchKey(e) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlight((h) => Math.min(h + 1, list.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlight((h) => Math.max(h - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (list[highlight]) choose(list[highlight])
    } else if (e.key === 'Escape') {
      e.preventDefault()
      choose(null)
    } else if (e.key === 'Tab') {
      setOpen(false)
    }
  }

  let lastGroup = null
  return (
    <div ref={root} className="relative inline-block">
      <button
        ref={button}
        type="button"
        id={id}
        role="combobox"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => (open ? setOpen(false) : openWith(''))}
        onKeyDown={onButtonKey}
        className={`flex items-center justify-between gap-2 rounded-md border border-slate-300 bg-white px-2 py-1 text-left text-sm text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60 ${className}`}
      >
        <span className="truncate">{shownLabel}</span>
        <span aria-hidden="true" className="text-[10px] text-slate-400">▾</span>
      </button>
      {open && (
        <div className="absolute left-0 z-30 mt-1 w-64 min-w-full rounded-md border border-slate-200 bg-white p-1 shadow-lg">
          <input
            autoFocus
            aria-label={`Search ${ariaLabel ?? 'options'}`}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value)
              setHighlight(0)
            }}
            onKeyDown={onSearchKey}
            placeholder="Type to search"
            className="mb-1 w-full rounded border border-slate-200 px-2 py-1 text-sm focus:border-neutral-900 focus:outline-none"
          />
          <ul role="listbox" aria-label={ariaLabel} className="max-h-60 overflow-y-auto">
            {list.length === 0 && <li className="px-2 py-1.5 text-xs text-slate-400">No matches</li>}
            {list.map((option, i) => {
              const heading = !query.trim() && option.group && option.group !== lastGroup ? option.group : null
              if (option.group) lastGroup = option.group
              const isSelected = option.empty ? value == null || value === '' : String(option.value) === String(value)
              return (
                <li key={option.empty ? '__empty' : `${option.group ?? ''}|${option.value}`} role="presentation">
                  {heading && (
                    <div className="px-2 pb-0.5 pt-1.5 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                      {heading}
                    </div>
                  )}
                  <div
                    role="option"
                    aria-selected={isSelected}
                    onMouseDown={(e) => e.preventDefault()}
                    onMouseEnter={() => setHighlight(i)}
                    onClick={() => choose(option)}
                    className={`flex cursor-pointer items-center justify-between gap-2 rounded px-2 py-1.5 text-sm ${
                      i === highlight ? 'bg-slate-100' : ''
                    } ${option.empty ? 'text-slate-500' : 'text-slate-700'} ${isSelected ? 'font-medium' : ''}`}
                  >
                    <span>{option.label}</span>
                    {option.hint && <span className="text-xs text-slate-400">{option.hint}</span>}
                  </div>
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </div>
  )
}
