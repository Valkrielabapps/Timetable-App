// Runs once before every test file (see vite.config.js's test.setupFiles).
// Adds jest-dom's matchers (toBeInTheDocument, toHaveTextContent, etc.) to
// Vitest's expect, so component tests can assert on rendered DOM the same
// readable way the wider React ecosystem does.
import '@testing-library/jest-dom'
import { beforeEach } from 'vitest'

// Prices show in rupees in India and dollars elsewhere (detectCurrency in
// src/lib/plans.js). Tests are written for an Indian visitor, whatever time
// zone the machine running them is in; currency.test.jsx clears this.
beforeEach(() => {
  try {
    window.localStorage.setItem('timetablz.currency', 'INR')
  } catch {
    // Not a browser-like test.
  }
})
