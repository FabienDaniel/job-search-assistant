import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { i18n } from '@lingui/core'
import { Trans } from '@lingui/react/macro'
import { plural } from '@lingui/core/macro'
import { intlLocale, resolveLocale } from '../i18n'

describe('resolveLocale', () => {
  it('prefers a supported stored choice over the browser', () => {
    expect(resolveLocale('en', ['fr-FR'])).toBe('en')
  })
  it('ignores an unsupported stored choice', () => {
    expect(resolveLocale('xx', ['fr-CA'])).toBe('fr')
  })
  it('takes the first shipped browser language', () => {
    expect(resolveLocale(null, ['de-DE', 'fr', 'en'])).toBe('fr')
  })
  it('falls back to English', () => {
    expect(resolveLocale(null, ['de-DE'])).toBe('en')
    expect(resolveLocale(null)).toBe('en')
  })
})

describe('messages', () => {
  afterEach(() => { cleanup(); i18n.loadAndActivate({ locale: 'en', messages: {} }) })

  it('renders source text with no provider and no catalog', () => {
    render(<Trans>Hello there</Trans>)
    expect(screen.getByText('Hello there')).toBeTruthy()
  })

  it('applies French plural rules, where zero is singular', () => {
    i18n.loadAndActivate({ locale: 'fr', messages: {} })
    const line = (n) => plural(n, { one: '# offre', other: '# offres' })
    expect(line(0)).toBe('0 offre')
    expect(line(2)).toBe('2 offres')
  })
})

describe('French dates and schedules', () => {
  afterEach(() => { vi.resetModules(); i18n.loadAndActivate({ locale: 'en', messages: {} }) })

  // time.js builds its day and month names at import, as the app does after loading the catalog.
  const frenchTime = async () => {
    const { messages } = await import('../locales/fr.po')
    i18n.loadAndActivate({ locale: 'fr', messages })
    vi.resetModules()
    return import('../time')
  }

  it('describes schedules in French', async () => {
    const { describeCron } = await frenchTime()
    expect(describeCron('0 3 * * *').text).toBe('tous les jours à 03:00')
    expect(describeCron('0 8 * * mon').text).toBe('chaque lundi à 08:00')
    expect(describeCron('0 8 1 * *').text).toBe('chaque mois le 1er à 08:00')
    expect(describeCron('0 8 2 * *').text).toBe('chaque mois le 2 à 08:00')
  })

  it('names French days and months in whenShort', async () => {
    const { whenShort } = await frenchTime()
    expect(whenShort(new Date('2026-09-05T05:00:00Z'))).toBe('sam. 05 sept. 05:00')
  })

  it('writes elapsed time in French', async () => {
    const { ago } = await frenchTime()
    expect(ago(new Date(Date.now() - 5 * 60000).toISOString())).toBe('il y a 5 min')
  })
})

describe('intlLocale', () => {
  afterEach(() => i18n.loadAndActivate({ locale: 'en', messages: {} }))

  it('keeps a pinned English format in English', () => {
    expect(intlLocale('en-GB')).toBe('en-GB')
  })
  it('ignores the pinned English format in French', () => {
    i18n.loadAndActivate({ locale: 'fr', messages: {} })
    expect(intlLocale('en-GB')).toBe('fr')
    expect((1204).toLocaleString(intlLocale('en-US'))).toMatch(/^1\s204$/)
  })
})
