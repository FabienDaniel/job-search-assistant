// The feed's names for job sources (Job.source). Apify sources are named by their board.
import { t } from '@lingui/core/macro'
import { apifySourceLabel } from './apifyBoards'

export const SOURCE_LABELS = {
  direct: t`Direct`, extension: t`Extension`, jobspy_linkedin: 'LinkedIn', jobspy_indeed: 'Indeed',
  jobspy_zip_recruiter: 'ZipRecruiter', jobspy_google: 'Google', levels_fyi: 'Levels', linkedin_personal: t`LinkedIn Personal`,
  linkedin_extension: t`LinkedIn Extension`, jobright: 'Jobright', freehire: 'FreeHire', caribbeanjobs: 'CaribbeanJobs', trulyremote: 'TrulyRemoteWork', behance: 'Behance', hollylist: 'Hollylist', wanacreate: t`Wana Create`, himalayas: 'Himalayas', eluta: 'Eluta', freework: 'Free-Work', dribbble: 'Dribbble', artstation: 'ArtStation', workwithindies: t`Work With Indies`, playwright_url: t`Company careers`, playwright_direct: t`Career page`,
}
// `boards` (useApifyBoards) names the `apify_<board>` sources.
export const srcLabel = (s, boards = []) => SOURCE_LABELS[s] || apifySourceLabel(boards, s) || s || ''
