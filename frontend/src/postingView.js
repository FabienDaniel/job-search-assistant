// Which view of a posting the Jobs pane opens first: the app's reader view or the live page.
import { openLink } from './linkKinds'

// Matches DEFAULT_SETTINGS["feed_reader_sources"] in backend/seed.py, used until the account's value loads.
export const DEFAULT_READER_SOURCES = 'jobspy_linkedin,linkedin_extension,linkedin_personal'

export const parseReaderSources = (value) =>
  new Set(String(value ?? '').split(',').map((s) => s.trim()).filter(Boolean))

// A job with no link has no live page to show, so it always opens in the reader.
export const defaultPostingView = (job, readerSources) => {
  if (!job) return 'live'
  if (!openLink(job) || readerSources.has(job.source)) return 'reader'
  return 'live'
}
