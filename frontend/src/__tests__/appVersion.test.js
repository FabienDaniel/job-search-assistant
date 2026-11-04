// @vitest-environment node
// The dashboard warns when its version differs from the one /health returns, so the
// version built into the dashboard has to be spelled exactly as the backend spells it.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, it, expect } from 'vitest'
import config from '../../vite.config.js'

describe('__APP_VERSION__', () => {
  it('matches the backend APP_VERSION', () => {
    const source = readFileSync(resolve(process.cwd(), '../backend/version.py'), 'utf8')
    const backend = source.match(/^APP_VERSION = "(.+)"$/m)[1]
    expect(JSON.parse(config.define.__APP_VERSION__)).toBe(backend)
  })
})
