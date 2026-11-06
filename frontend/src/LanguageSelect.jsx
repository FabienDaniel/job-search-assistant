import { t } from '@lingui/core/macro'
import { LANGUAGES, currentLocale, setLocale } from './i18n'
import { Select } from './ui'

export default function LanguageSelect({ width = '260px' }) {
  return <Select value={currentLocale()} options={LANGUAGES} onPick={setLocale} width={width} ariaLabel={t`Language`} />
}
