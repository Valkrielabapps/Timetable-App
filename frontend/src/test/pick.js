import { fireEvent, screen } from '@testing-library/react'

/**
 * Choose an option from a SearchableSelect the way a person would: open it,
 * then click the option. `optionText` is the option's label (its hint, if
 * any, is ignored).
 */
export function pick(comboboxName, optionText) {
  fireEvent.click(screen.getByRole('combobox', { name: comboboxName }))
  const option = screen
    .getAllByRole('option')
    .find((o) => (o.firstChild?.textContent ?? o.textContent) === optionText)
  if (!option) throw new Error(`No option "${optionText}" in ${comboboxName}`)
  fireEvent.click(option)
}

/** The option labels a SearchableSelect offers, in order. Leaves it open. */
export function optionsOf(comboboxName) {
  fireEvent.click(screen.getByRole('combobox', { name: comboboxName }))
  return screen.getAllByRole('option').map((o) => o.firstChild?.textContent ?? o.textContent)
}
