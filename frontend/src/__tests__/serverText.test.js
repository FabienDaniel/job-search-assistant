import { describe, it, expect, afterEach, vi } from 'vitest'
import { i18n } from '@lingui/core'
import { serverText } from '../serverText'

describe('serverText in English', () => {
  it('keeps backend wording, including through a prefix and an interval', () => {
    expect(serverText('Job not found')).toBe('Job not found')
    expect(serverText('PDF generation failed: boom')).toBe('PDF generation failed: boom')
    expect(serverText('Every 60 min (search override)')).toBe('Every 60 min (search override)')
  })
  it('passes through what it does not list', () => {
    expect(serverText('ids must be a list')).toBe('ids must be a list')
    expect(serverText('wrong_pin')).toBe('wrong_pin')
    expect(serverText(undefined)).toBeUndefined()
  })
  it('never treats an inherited object key as a message', () => {
    expect(serverText('constructor')).toBe('constructor')
  })
})

describe('serverText in French', () => {
  afterEach(() => { vi.resetModules(); i18n.loadAndActivate({ locale: 'en', messages: {} }) })

  const french = async () => {
    const { messages } = await import('../locales/fr.po')
    i18n.loadAndActivate({ locale: 'fr', messages })
    vi.resetModules()
    return (await import('../serverText')).serverText
  }

  it('translates listed messages and keeps upstream text as sent', async () => {
    const text = await french()
    expect(text('Job not found')).toBe('Offre introuvable')
    expect(text('PDF generation failed: boom')).toBe('Échec de la génération du PDF : boom')
    expect(text('Every 60 min')).toBe('Toutes les 60 min')
  })

  it('leaves machine codes alone so logic comparing them keeps working', async () => {
    const text = await french()
    expect(text('scheduled_scrape_running')).toBe('scheduled_scrape_running')
    expect(text('pin_required')).toBe('pin_required')
  })
})
