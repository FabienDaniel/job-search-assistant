import { i18n } from '@lingui/core'
import { TransNoContext } from '@lingui/react/server'

// The Lingui macro imports this Trans in place of the provider-based one.
// A language change reloads the page, so no component needs a re-render signal.
export const Trans = (props) => <TransNoContext {...props} lingui={{ i18n }} />
