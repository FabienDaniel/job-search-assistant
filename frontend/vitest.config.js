// Unit-test config for the frontend. Deliberately separate from vite.config.js
// so the app build is untouched: `npm run build` never loads this file.
//
// Run it with `bash tests/tools/fe-test.sh` (Node lives only in Docker here).
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { lingui } from '@lingui/vite-plugin'
import { fileURLToPath } from 'node:url'

// TZ is pinned to UTC because time.js's `whenShort` reads a Date with LOCAL
// getters — the same instant renders as a different day/hour in another zone, so
// the assertions would be machine-dependent otherwise. fe-test.sh also passes
// `-e TZ=UTC` to the container, which is what actually reaches the test workers;
// this line covers a direct `npx vitest run` in an already-UTC-less shell.
process.env.TZ = 'UTC'

export default defineConfig({
  plugins: [react({ babel: { plugins: ['@lingui/babel-plugin-lingui-macro'] } }), lingui()],
  resolve: { alias: { 'jn-i18n-trans': fileURLToPath(new URL('./src/i18nTrans.jsx', import.meta.url)) } },
  define: { __DEMO__: false },
  // the demo bundles the backend's template files from the sibling directory
  server: { fs: { allow: ['..'] } },
  test: {
    environment: 'jsdom',
    setupFiles: ['src/__tests__/setup.js'],
    globals: true,
    include: ['src/**/__tests__/**/*.test.{js,jsx}'],
    // CSS imports (ui.jsx pulls theme.css) resolve to an empty module — the
    // tests assert logic, never computed style.
    css: false,
    clearMocks: true,
  },
})
