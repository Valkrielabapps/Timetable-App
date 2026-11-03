// Imported from 'vitest/config' rather than plain 'vite' so this single
// file can also carry Vitest's `test` option with type support - it's a
// drop-in superset of Vite's own defineConfig, so `vite dev`/`vite build`
// behave exactly as before; only `vitest` reads the extra `test` block.
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Vitest 2.1.9 runs tests through its own bundled vite@5 (via vite-node),
  // separate from this project's root vite@8. That version split means
  // @vitejs/plugin-react's babel transform isn't reliably applied when
  // running under `vitest`, so Vite falls back to esbuild's default
  // *classic* JSX transform (React.createElement, requiring `React` in
  // scope) instead of the automatic runtime the app actually uses - surfacing
  // as "ReferenceError: React is not defined" in component files that never
  // import React. Pinning esbuild's jsx mode here makes the automatic
  // runtime explicit regardless of which Vite copy ends up doing the
  // transform, so `vite dev`/`vite build` (already automatic by default)
  // and `vitest` both render JSX the same way.
  esbuild: {
    jsx: 'automatic',
  },
  server: {
    proxy: {
      // Forward API calls to the FastAPI backend during local dev, so the
      // frontend can call e.g. fetch('/api/schools') without hardcoding a
      // host/port.
      '/api': 'http://localhost:8000',
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
  },
})
