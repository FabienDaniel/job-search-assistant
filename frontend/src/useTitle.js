import { useEffect } from 'react'
import { t } from '@lingui/core/macro'
import { useLocation } from 'react-router-dom'

const APP = t`JobNavigator`

// Longest prefix wins, so /resumes/:id falls back to "Résumé" until the
// editor loads and names the actual document.
const ROUTES = [
  ['/feed', t`Jobs`],
  ['/searches', t`Searches`],
  ['/companies', t`Companies`],
  ['/applications', t`Applications`],
  ['/resumes', t`Résumés`],
  ['/cover-letters', t`Cover Letters`],
  ['/persona', t`Persona`],
  ['/stats', t`Stats`],
  ['/settings', t`Settings`],
  ['/toasts', t`Toast lab`],
  ['/', t`Jobs`],
]

export const titleFor = (path) => {
  const hit = ROUTES.filter(([p]) => path === p || path.startsWith(p === '/' ? '/#never' : p + '/'))
    .sort((a, b) => b[0].length - a[0].length)[0]
  return hit ? hit[1] : (ROUTES.find(([p]) => p === path) || [])[1]
}

/** Name the tab after the screen. Editors call useTitle() to refine it. */
export function TitleSync() {
  const { pathname } = useLocation()
  useEffect(() => {
    const name = titleFor(pathname)
    document.title = name ? `${name} · ${APP}` : t`${APP} Dashboard`
  }, [pathname])
  return null
}

/** Override the route title with the document actually on screen. */
export function useTitle(name) {
  useEffect(() => {
    if (!name) return undefined
    const prev = document.title
    document.title = `${name} · ${APP}`
    return () => { document.title = prev }
  }, [name])
}
