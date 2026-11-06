import { t } from '@lingui/core/macro'

// The backend writes its messages in English. These are the ones a user can reach through
// the screens. Validation errors only an API client can trigger stay in English on purpose.
const EXACT = {
  'Account not found': t`Account not found`,
  'Application not found': t`Application not found`,
  'Company not found': t`Company not found`,
  'Could not delete this company — another record still references it': t`Could not delete this company — another record still references it`,
  'Could not delete this search — another record still references it': t`Could not delete this search — another record still references it`,
  'Could not extract enough text from PDF. It may be image-based.': t`Could not extract enough text from PDF. It may be image-based.`,
  'DOCX generation failed': t`DOCX generation failed`,
  'Interview not found': t`Interview not found`,
  'Invalid API key': t`Invalid API key`,
  'Job not found': t`Job not found`,
  'LLM returned invalid JSON. Try again or enter data manually.': t`LLM returned invalid JSON. Try again or enter data manually.`,
  'LinkedIn is shared from the account owner; only the owner can refresh the session': t`LinkedIn is shared from the account owner; only the owner can refresh the session`,
  'Linked job has no description or cached page text': t`Linked job has no description or cached page text`,
  'Linked job not found': t`Linked job not found`,
  'No account': t`No account`,
  'No account to link': t`Pick an account first — there is no account to link this chat to.`,
  'No cached page available': t`No cached page available`,
  'No JobSpy sources configured': t`No JobSpy sources configured`,
  'No levels.fyi URL configured': t`No levels.fyi URL configured`,
  'No posting URL captured for this job': t`No posting URL captured for this job`,
  'No scrape URLs configured': t`No scrape URLs configured`,
  'Not found': t`Not found`,
  'Only PDF files are accepted': t`Only PDF files are accepted`,
  'Only the account owner can change section policies': t`Only the account owner can change section policies`,
  'PDF too large (max 10 MB)': t`PDF too large (max 10 MB)`,
  'Posting is rendered client-side — needs the extension': t`Posting is rendered client-side — needs the extension`,
  'Posting returned no content': t`Posting returned no content`,
  'Resume has insufficient text for scoring': t`Resume has insufficient text for scoring`,
  'Resume has no linked job or saved job description': t`Resume has no linked job or saved job description`,
  'Resume not found': t`Resume not found`,
  'Run not found': t`Run not found`,
  'Search not found': t`Search not found`,
  'Send a resume_id, or upload a PDF file': t`Send a resume_id, or upload a PDF file`,
  'Test run not found': t`Test run not found`,
  'Too many failed attempts': t`Too many failed attempts`,
  'URL not allowed': t`URL not allowed`,
  'name is required': t`Name is required`,
  // scheduled job names (SCHEDULE_NAMES in backend/main.py)
  'Scrape all searches & companies': t`Scrape all searches & companies`,
  'Check Gmail for replies': t`Check Gmail for replies`,
  'Send daily Telegram digest': t`Send daily Telegram digest`,
  'Back up database (pg_dump)': t`Back up database (pg_dump)`,
  'Clean up stale skipped jobs': t`Clean up stale skipped jobs`,
  'Auto-reject stale applications': t`Auto-reject stale applications`,
  'Send telemetry (what Settings › Telemetry allows)': t`Send telemetry (what Settings › Telemetry allows)`,
  'Scrape all searches & companies': t`Scrape all searches & companies`,
  'Check Gmail for replies': t`Check Gmail for replies`,
  'Send daily Telegram digest': t`Send daily Telegram digest`,
  'Back up database (pg_dump)': t`Back up database (pg_dump)`,
  'Clean up stale skipped jobs': t`Clean up stale skipped jobs`,
  'Auto-reject stale applications': t`Auto-reject stale applications`,
  'Send telemetry (what Settings › Telemetry allows)': t`Send telemetry (what Settings › Telemetry allows)`,
}

// Messages ending in text from elsewhere, such as an upstream error. That text stays as sent.
const PREFIXED = [
  ['Could not fetch posting: ', (rest) => t`Could not fetch posting: ${rest}`],
  ['Failed to process PDF: ', (rest) => t`Failed to process PDF: ${rest}`],
  ['LLM extraction failed: ', (rest) => t`LLM extraction failed: ${rest}`],
  ['PDF generation failed: ', (rest) => t`PDF generation failed: ${rest}`],
  ['These settings are managed by the account owner: ', (rest) => t`These settings are managed by the account owner: ${rest}`],
]

const INTERVAL = /^Every (\d+) min( \((search|company) override\))?$/

/** The user's language for a backend message, or the message itself when it is not listed. */
export function serverText(text) {
  if (typeof text !== 'string') return text
  if (Object.hasOwn(EXACT, text)) return EXACT[text]
  for (const [prefix, render] of PREFIXED) {
    if (text.startsWith(prefix)) return render(text.slice(prefix.length))
  }
  const every = INTERVAL.exec(text)
  if (every) {
    const minutes = every[1]
    if (every[3] === 'search') return t`Every ${minutes} min (search override)`
    if (every[3] === 'company') return t`Every ${minutes} min (company override)`
    return t`Every ${minutes} min`
  }
  return text
}
