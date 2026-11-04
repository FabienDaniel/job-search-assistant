import React from 'react'
import ReactDOM from 'react-dom/client'
import { initI18n } from './i18n'
import { loadDemo } from './demoHooks'

async function boot() {
  await initI18n()
  // Demo build only: __DEMO__ is a build-time constant, so the branch (and the
  // demo modules) are dropped from the normal bundle.
  if (__DEMO__) {
    const { installDemo } = await loadDemo('install.js')
    await installDemo()
  }
  // Imported after the catalog because screens read translated labels at import.
  // base.css stays after App so the stylesheet cascade order does not change.
  const { default: App } = await import('./App')
  await import('./base.css')
  ReactDOM.createRoot(document.getElementById('root')).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  )
}

boot()
