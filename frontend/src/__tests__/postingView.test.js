// The first view of a posting in the Jobs pane (postingView.js) and its setting (feed_reader_sources).
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { DEFAULT_READER_SOURCES, defaultPostingView, parseReaderSources } from '../postingView'

const linkedin = { source: 'jobspy_linkedin', url: 'https://www.linkedin.com/jobs/view/1' }
const indeed = { source: 'jobspy_indeed', url: 'https://www.viseo.com/job/1' }

describe('posting view', () => {
  it('opens listed sources in the reader and the others on the live page', () => {
    const set = parseReaderSources(DEFAULT_READER_SOURCES)
    expect(defaultPostingView(linkedin, set)).toBe('reader')
    expect(defaultPostingView(indeed, set)).toBe('live')
  })

  it('opens everything live when no source is listed', () => {
    const set = parseReaderSources('')
    expect(defaultPostingView(linkedin, set)).toBe('live')
    expect(defaultPostingView(indeed, set)).toBe('live')
  })

  it('opens a job with no link in the reader', () => {
    expect(defaultPostingView({ source: 'jobspy_indeed', url: null }, parseReaderSources(''))).toBe('reader')
  })

  it('parses the stored list loosely', () => {
    expect([...parseReaderSources(' jobspy_indeed , ,jobspy_google')]).toEqual(['jobspy_indeed', 'jobspy_google'])
    expect(parseReaderSources(undefined).size).toBe(0)
  })

  it('uses the same default as the backend seed', () => {
    const seed = readFileSync(resolve(process.cwd(), '../backend/seed.py'), 'utf8')
    const m = seed.match(/"feed_reader_sources": \(\s*"([^"]*)"/)
    expect(m && m[1]).toBe(DEFAULT_READER_SOURCES)
  })
})
