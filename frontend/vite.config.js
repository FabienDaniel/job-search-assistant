import { readFileSync } from 'node:fs'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const pkg = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf8'))
// Releases are named major.minor ("3.2"), with a patch when needed ("3.2.1"). package.json
// keeps full semver for npm ("3.2.0"). The result must equal the backend's APP_VERSION,
// because the dashboard compares the two and warns when they differ.
const appVersion = pkg.version.replace(/\.0$/, '')

export default defineConfig({
  base: process.env.VITE_DEMO === '1' ? '/JobNavigator-demo/' : '/',
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(appVersion),
    __DEMO__: JSON.stringify(process.env.VITE_DEMO === '1'),
  },
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    }
  }
})
