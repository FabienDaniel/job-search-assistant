import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { i18n } from '@lingui/core'
import { Trans } from '@lingui/react/macro'
import { plural } from '@lingui/core/macro'
import { resolveLocale } from '../i18n'

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
