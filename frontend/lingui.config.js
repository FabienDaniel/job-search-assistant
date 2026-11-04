import { defineConfig } from '@lingui/cli'
import { formatter } from '@lingui/format-po'

export default defineConfig({
  // No line numbers: otherwise any edit that moves code would make the catalogs look stale in CI.
  format: formatter({ lineNumbers: false }),
  sourceLocale: 'en',
  locales: ['en', 'fr'],
  fallbackLocales: { default: 'en' },
  catalogs: [{
    path: '<rootDir>/src/locales/{locale}',
    include: ['<rootDir>/src'],
    exclude: ['**/__tests__/**', '**/locales/**', '**/node_modules/**'],
  }],
  // Screens render <Trans> without a provider. See src/i18nTrans.jsx.
  runtimeConfigModule: { Trans: ['jn-i18n-trans', 'Trans'] },
})
