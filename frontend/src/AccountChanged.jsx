import React, { useEffect, useState } from 'react'
import { t } from '@lingui/core/macro'
import { Trans } from '@lingui/react/macro'
import api from './api'
import { Button, Heading, Helper, ModalPanel } from './ui'
import { useTheme, themeAttrs } from './theme'
import './theme.css'

// QA F7 / R6-01: this tab shows one account, but the browser is now on another
// (a switch in another tab, or the server refused a write with 409
// `account_changed`). api.js already stops every write; this notice blocks the
// screen until the tab reloads into the account the browser is on. No Escape,
// no scrim close: anything typed here would be written into the wrong account.
export default function AccountChanged({ account }) {
  const look = useTheme()
  const [name, setName] = useState(account?.name || '')
  useEffect(() => {
    if (name) return undefined
    let live = true
    // a read is still allowed: ask who the browser is now
    api.get('/auth/me').then(({ data }) => { if (live && data?.account?.name) setName(data.account.name) }).catch(() => { /* the plain wording stays */ })
    return () => { live = false }
  }, [name])
  const who = name || t`another account`
  return (
    <ModalPanel width={420} title={t`Account changed`} zIndex={10000} labelledBy="jn-acctchanged-title" trapFocus
      scrimProps={{ className: 'jn-v2', 'data-account-changed': '', ...themeAttrs(look) }}
      style={{ padding: '24px 26px 20px', gap: 14 }}>
      <Heading size={19} id="jn-acctchanged-title"><Trans>This tab was switched to {who}</Trans></Heading>
      <Helper>
        <Trans>Another tab switched this browser to {who}. Nothing more is saved from this tab — reload it to carry on as {who}.</Trans>
      </Helper>
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <Button onClick={() => window.location.reload()} ariaLabel={t`Reload as ${who}`}><Trans>Reload</Trans></Button>
      </div>
    </ModalPanel>
  )
}
