import { defineConfig } from '@lingui/cli'

export default defineConfig({
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
