import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, it, expect } from 'vitest'

// lingui compile --strict cannot catch this: the English fallback counts as a translation.
const untranslated = (po) => [...po.matchAll(/^msgid "(.+)"\nmsgstr ""$/gm)].map((m) => m[1])

describe('translation catalogs', () => {
  it('has French for every message', () => {
    const po = readFileSync(resolve(process.cwd(), 'src/locales/fr.po'), 'utf8')
    expect(untranslated(po)).toEqual([])
  })
})
