# backend/scraper

This package turns job searches and company career pages into `Job` rows, once per account. It fetches boards, APIs and career sites, then filters and deduplicates the postings and saves them under the account that owns the search or company. Links that point to the same posting are joined into one job.

LLM scoring, alerts, the dashboard and run tracking sit outside this package. They call in through the entry points below.

Most modules carry a detailed docstring. This file gives the map and points at them.

```
backend/scraper/
  orchestrator.py    entry points, run fan-out, ScrapeLog rows and run summaries
  search_modes.py    the table of search modes (one entry per source)
  targets.py         shared fetches across accounts, target keys, due-ness
  sources/           one module per search mode, plus company_pages.py
  ats/               one handler per applicant tracking system, used by company_pages
  _shared/           ingest helpers: filters, dedup, posting identity, enrichment, safety
```

## Entry points

| Caller | Calls | What it does |
|---|---|---|
| `scheduler.run_all_scrapes` (interval job) | `orchestrator.run_all()` | All due searches and companies of every account |
| `POST /api/scrape/run-all` (`main.py`) | `orchestrator.run_all(force=True, account_ids=[me])` | Everything for the caller's account, ignoring intervals |
| `POST /api/searches/{id}/run` (`api/routes_searches.py`) | `orchestrator._run_search_by_id` | One search, caller's account only, no shared fetch |
| `POST /api/scrape/company/{id}` (`main.py`) | `company_pages.scrape_single_career_page` + `record_company_scrape_log` | One company |
| `POST /api/searches/{id}/test` | `sources.<module>.preview(search, db)` | Dry run for the Test button. Writes no jobs |
| `POST /api/companies/{id}/test-scrape` (`api/routes_companies.py`) | `company_pages.preview(company, db)` | Dry run of a company. Writes no jobs |
| `POST /api/jobs/linkedin-import` (`api/routes_jobs.py`) | `sources.linkedin_extension.enrich` | LinkedIn job ids pushed by the Chrome extension |

`orchestrator.run_search(search)` dispatches one search to its source module. `orchestrator.run_company(company)` does the same for one company.

The scraper does not report progress itself. It returns result dicts and writes `ScrapeLog` rows. The callers wrap runs in `job_monitor.tracked_run` or `job_monitor.launch_background`, under job types `scrape_all`, `search_run` and `company_scrape`. All three share the `scraping` limiter. When a scraping run ends, `job_monitor` fires the `on_scrape_finished` hooks. `main.py` registers `scheduler.lookup_after_scrape` there, which runs the LinkedIn employer-link lookup.

## Life of a scheduled run

```
run_all
  load_active (unscoped, every account)  ->  searches, companies
  drop extension modes, manual runs in flight, invalid configs
  group_targets + split_search_targets   ->  targets
  for each due target:
      shared = shared_fetch_for(key)         (shareable modes only)
      for each subscriber, in account_session(account):
          run_search(search, shared=shared)  ->  source.run fetches once, ingests per account
          _record_search_log                 ->  ScrapeLog row, last_run_at
  scoring sweep per account (acting_as)      ->  analyzer.cv_scorer.analyze_unscored_jobs
  company_pages.scrape_career_pages          ->  same pattern for companies
  first run of an account: mark its existing jobs seen
```

Details that matter:

- Each subscriber works in a fresh session of its own account (`accounts.background.account_session`). The batch session that loaded every account's rows is never used to write.
- One subscriber failing does not stop the others. Errors outside a source's result come back in `run_all(...)["errors"]`.
- The rows of one fetch share a `run_id`, so the run history can group them.
- `last_run_at` is stamped on every finished attempt, including empty and failed ones. Otherwise a broken search would run on every tick.
- A run is a warning (`orchestrator.run_is_warning`) when a board failed, when a configured board returned no rows, or when nothing was found and no error was given.

## Search modes

`search_modes.SEARCH_MODES` is the single table of modes. The run dispatch, the API's mode and source checks, the Test path and shared fetches all read it. `frontend/src/searchModes.js` mirrors it, and `backend/tests/test_search_modes.py` fails when the two differ.

| Mode | Module | Shared | Technique | Needs |
|---|---|---|---|---|
| `keyword` | `jobspy` | yes | python-jobspy library over LinkedIn, Indeed, ZipRecruiter, Google, Glassdoor, Bayt, Naukri, BDJobs | |
| `levels_fyi` | `levelsfyi` | yes | Playwright on levels.fyi | URL |
| `linkedin_personal` | `linkedin_personal` | no, own session | Playwright with the account's LinkedIn cookies | |
| `jobright` | `jobright` | no, own session | Jobright REST API with the account's login | |
| `freehire` | `freehire` | yes | freehire.me REST API | term or URL |
| `apify` | `apify` | no, billed per account | Apify actors (Indeed, LinkedIn, Glassdoor, Behance, career sites) | term and a board. Paid |
| `caribbeanjobs` | `caribbeanjobs` | yes | HTML and JSON-LD over httpx | term or URL |
| `trulyremote` | `trulyremote` | yes, one global key | `llms-full.txt` roster plus `.md` job pages | |
| `creative` | `creative` | no | six boards through `_shared/job_boards.py` | term and a board |
| `himalayas` | `himalayas` | no | JSON API through `_shared/job_boards.py` | term |
| `eluta` | `eluta` | no | RSS plus job pages through `_shared/job_boards.py`, heavily rate limited | term |
| `linkedin_extension`, `extension` | none | | jobs arrive by push from the Chrome extension | |

The `SearchMode` flags are documented on the dataclass. `config_error(search)` gives the human reason a search cannot run.

## Shared fetches across accounts

`targets.py` lets several accounts with identical searches or companies share one fetch. Read its module docstring for the key of each mode.

- A target is a group of searches or companies with the same key (`search_key`, `company_key`). Modes that read an account's own session or bill an account get a key with the search id, so they are never shared.
- `SharedFetch` holds one fetch. The first subscriber fetches through `shared.get(fn)`, or `shared.get_sync(fn)` from JobSpy's worker thread. Later subscribers get a deep copy, so one account's ingest cannot change what the next account sees.
- `SharedFetch.params` holds the largest `fetch_params` among subscribers (for example `results_wanted`). Each account trims its own copy.
- `SharedFetch.memo` caches raw follow-up pages that are the same for everyone (detail pages, the `<source>_halt` throttle flag).
- `shared_fetch_for` keeps fetches for `REUSE_SECONDS` (10 minutes), so another run in that window reuses the result.
- `split_search_targets` splits JobSpy targets whose `hours_old` or `results_wanted` are too far apart, so one account's 500 rows over 30 days never inflates another's 50 rows over 1 day.
- A target is due when any subscriber is due under its own interval (`search_target_due`, `company_target_due`).

The rule: nothing account-specific goes into the shared part. Filters, dedup and saving happen per account, after the fetch.

## Sources

Every search source exposes `async run(search, ...) -> dict` returning at least `jobs_found`, `new_jobs`, `error` and `duration`, and usually `source_breakdown` (one entry per board). Each also exposes `async preview(search, db)` for the Test button, which reports what every filter layer would do and saves nothing. `test_search_modes.py` checks both exist for every runnable mode. The keyword Test runs inline in the request. The others run in the background and are polled.

| Module | Notes |
|---|---|
| `jobspy.py` | Runs `scrape_jobs` in a worker thread. Known block messages for ZipRecruiter and Google. Fills LinkedIn descriptions through `_shared/employer_text`. Rejected rows are stored as `ignored`. |
| `levelsfyi.py` | Playwright, because the site's API responses are encrypted. Retries on zero results. Job text comes from `_shared/levels_jobs`. |
| `linkedin_personal.py` | The account's recommended and top-applicant collections. Human-like delays, session-expiry and rate-limit errors. |
| `linkedin_extension.py` | No `run()`. `enrich(ids)` reads LinkedIn's Voyager API from a logged-in Playwright page. Progress is kept in memory per account for `GET /api/jobs/linkedin-import/progress`. |
| `jobright.py` | Logs in with the account's credentials. Pages of 20 with a 7 s delay. Replaces Jobright's AI summary with the employer's own text when it can. |
| `freehire.py` | Open API. Descriptions and employer links come in the search response, so there are no detail fetches. |
| `apify.py` | Presets in `PRESETS`. Each run is capped by `maxItems`, a USD charge cap and a 15 minute timeout. Filtered rows are not stored. |
| `caribbeanjobs.py` | Detects Cloudflare challenges. Detail pages run at concurrency 2 with jitter and honour `Retry-After`. |
| `trulyremote.py` | The template CONTRIBUTING.md recommends for a new source. The roster is cached in-process for as long as Cache-Control allows. |
| `creative.py`, `himalayas.py`, `eluta.py` | Describe each board as a `Board` and hand it to `_shared/job_boards.run` and `preview`. That module is the simplest way to add a no-login JSON or feed board. |
| `company_pages.py` | Company career pages. See the next section. |

## Company career pages and ATS handlers

`sources/company_pages.py` scrapes each company's `scrape_urls`. Each URL goes to the handler of the applicant tracking system it belongs to, or to the generic Playwright scraper.

Handler contract (`ats/<name>.py`):

- `is_<name>(url) -> bool`, matched on the hostname.
- `async scrape(url, debug=False)` returns job dicts with `title` and `url`, and optionally `location`, `locations`, `arrangement` and `description`. With `debug=True` it returns `(jobs, rejected)`. Playwright handlers also take `browser` and `max_pages`.
- Rows are checked with `_shared/filters._validate_job`. A board that answers 404 or 410 raises `BoardNotFoundError` through `_shared/errors.raise_if_board_gone`, so a closed company shows as an error rather than an empty board.

| Handler | Technique |
|---|---|
| `greenhouse`, `lever`, `ashby`, `rippling`, `smartrecruiters`, `workday`, `oracle_hcm` | Public JSON APIs. Filters from the URL are applied client-side where the API ignores them. Workday splits a search that hits its result ceiling by facet. |
| `phenom` | POST to a per-company endpoint, stored as `POST\|{api_url}\|{json}` |
| `talentbrew` | AJAX endpoint of legacy TalentBrew pages |
| `amazon`, `uber` | The JSON endpoints their own search pages render from |
| `meta`, `google` | Playwright DOM scraping with pagination |
| `generic` | Playwright fallback: link heuristics, pagination, the company's `wait_for_selector` |

`ats/registry.py` holds the one ordered list of handlers (`HANDLERS`). `detect(url)` picks the handler, `scrape_type(url)` gives its label for the dashboard chip, target keys and telemetry, and `needs_browser(urls)` decides whether Chromium is launched at all, so a company that only uses API handlers never starts a browser. The order matters: checks that can match any host (Phenom's `POST|` spec, TalentBrew's AJAX path, Oracle's `/sites/` path) come first. `detectAts` in `frontend/src/screens/Companies.jsx` mirrors the list for the live chip.

`company_pages._dispatch_ats` calls the registry's handler or the generic reader. `_fetch_postings` is the fetch half that a shared company target runs once.

`ats/_descriptions.py` fetches a job's description after the listing. `_fetch_job_description` tries the ATS's own detail API first (`_fetch_description_ats`), then falls back to the page HTML through the SSRF guard, rejecting bot walls and script blobs.

## The ingest pipeline

Every source follows the same order. `_shared/job_boards.run` and `company_pages.scrape_single_career_page` are the clearest examples.

1. Fetch, through `shared.get` when there is a shared fetch.
2. Filter titles and companies: `search_title_filters`, `title_kept` (or `title_filter_hit` for a caller's own wording), `company_included`, `build_search_exclude_sets` (companies: `_apply_company_filters`), all in `_shared/filters.py`.
3. Skip known jobs: `models.db.get_existing_external_ids` and `_shared/dedup.make_external_id`.
4. Fetch details only for rows that passed and are new.
5. `await _shared/analysis.prefetch_h1b(companies)` before the first `db.add`, so per-job lookups hit the cache.
6. Build the `Job` with `make_content_hash`, then `analyze_inline(job, db=db)` for H-1B, salary, work arrangement and location.
7. A job whose description hits a body-exclusion phrase, or that is dropped after its page was read, goes through `mark_ignored(job)`. It is stored so its URL is never read again.
8. `db.add` and flush inside `db.begin_nested()`. An `IntegrityError` means a duplicate and is skipped. The flush fires the `posting_links` listener (next section).
9. Count with `posting_links.counts_as_new(job)`, so a copy of a known posting is not "+1 new".
10. Stamp `last_run_at` or `last_scraped_at`, commit, and `log_activity("scrape", ...)`.

After the source returns, the orchestrator writes the `ScrapeLog` row. When the search has auto-scoring on and found new jobs, it runs `analyzer.cv_scorer.analyze_unscored_jobs`, which also sends the Telegram alert for jobs above the fit threshold.

## One job per posting

One posting reaches the app through many links: the company's board, LinkedIn, Jobright, levels.fyi, a tracking redirect. These modules join them.

- `_shared/postings.py`: `posting_key(url)` reads the posting's identity out of a link (`greenhouse:8686811002`) through a chain of per-system readers. `READER_VERSION` must be bumped when a reader changes what key a link gets. `seed.migrate_posting_keys` then re-keys stored jobs on the next boot.
- `_shared/posting_links.py`: a SQLAlchemy `before_flush` listener (`install_posting_links`, called from `models/db.py`) that gives every new job a `posting_key`, `apply_url` and `link_kind`, then links it to the posting it repeats. It applies three rules: same key, same role proven from the text within 60 days, or a board-only copy that a newly arrived employer posting supersedes. Copies get `duplicate_of` and `copy_kind`.
- `_shared/same_role.py`: decides whether two texts with one company and title are one role. Near enough is not enough: the texts must match apart from places, codes and pay, and a company template proves nothing.
- `_shared/dedup.py`: URL normalisation (tracking parameters come from settings) and the `external_id` and `content_hash` hashes.
- `_shared/link_kinds.py`: `direct`, `board` or `easy_apply` for every job. A new board's host goes in `BOARD_HOSTS`.

## Posting status and safety

- `_shared/still_open.py`: checks on demand whether a posting is still open (when a job is opened, or a résumé is made for it), cached for a day. A bot wall or an error gives `unknown`, never closed.
- `_shared/missing_postings.py`: marks a company's posting closed when it is missing from two full scrapes in a row. Only handlers that return the whole board count (`_full_board`).
- `_shared/url_safety.py`: SSRF guard. `safe_get` resolves the host once and connects to the checked IP, so DNS rebinding cannot reach internal addresses. Use it for any URL a user can supply.
- `_shared/bot_wall.py`: recognises Cloudflare and login interstitials, so they are never stored as job text.

## Other shared modules

| Module | Responsibility |
|---|---|
| `_shared/browser.py` | Playwright lifecycle (`_get_browser`, `_new_page`, `_close_page`) and stealth settings |
| `_shared/urls.py` | Strict hostname matching (`host_matches`), path matching, apply-link cleanup |
| `_shared/html_text.py` | HTML descriptions to plain text |
| `_shared/page_cache.py` | Fetches a job's posting page (HTTP, then Playwright for thin pages) and stores it as clean HTML and text for the reader view, scoring and tailoring. Refuses unsafe URLs and bot walls |
| `_shared/errors.py` | `BoardNotFoundError` and `raise_if_board_gone` |
| `_shared/employer_text.py` | Replaces a board's summary with the employer's own description |
| `_shared/levels_jobs.py` | Reads a levels.fyi job from its page's `__NEXT_DATA__` |
| `_shared/linkedin_session.py` | Signs the main or mock LinkedIn account in through Playwright, relays LinkedIn's emailed PIN, and saves the cookie jar the LinkedIn sources read. Also the CLI `python -m backend.refresh_linkedin_session` |
| `_shared/linkedin_lookup.py` | Finds the employer link of LinkedIn listings through the mock account's session, never the user's own. Runs after every scrape. |

## Extending

Follow the recipes in `CONTRIBUTING.md`: "Add a job-board source" and "Add an ATS handler". A new ATS handler is registered once, in `ats/registry.HANDLERS`. `test_ats_registry.py` fails when an `ats/<name>.py` with an `is_<name>` check is missing from it.

## Tests

117 files in `backend/tests/` import this package. Their names follow the area:

- Core: `test_orchestrator`, `test_search_modes`, `test_mt_shared_scrape`, `test_shared_fetch_reuse`.
- Sources: `test_sources_*` and `test_<source>_*`.
- Handlers: `test_ats_*`.
- `_shared/`: `test_postings`, `test_posting_links`, `test_same_role`, `test_shared_*`, `test_url_safety` and similar.

```bash
docker compose exec -T backend sh -c "cd /app && python -m pytest backend/tests -q -p no:cacheprovider -m 'not live'"
docker compose exec -T backend sh -c "cd /app && python -m pytest backend/tests/test_ats_lever.py -q -p no:cacheprovider -m 'not live'"
```

Use the `test_db` or `api_client` fixture in any test that touches the database. Without it the session points at the live Postgres.

## Known issues

These are places where scraping logic lives outside this package, or where the package depends on layers above it.

- **JobSpy and company filters outside `_shared/filters.py`.** JobSpy runs and previews filter titles with a pandas mask (`jobspy.apply_title_filters`) that reads include keywords as a regular expression, where `title_kept` reads them as plain text. `company_pages` applies its per-company layers inline, and its preview repeats them to report a reason per row.
- **Posting-URL parsing in a route.** `api/routes_applications.extract_posting` and its helpers (`_company_from_url`, `_known_posting`) read a posting's title and company from its URL inside the API layer.
- **Extension company excludes.** `routes_jobs.save_from_extension` and `linkedin_extension.enrich` check only the extension search's own company exclude list, not the global list or the active companies that `build_search_exclude_sets` adds.
- **LinkedIn cookie paths.** The per-account jar and PIN file paths (`linkedin_*_cookies`, `linkedin_pin_file`) live in `accounts/credentials.py` with the other per-account credential paths.
- **Smaller items.** `backend/countries.py` is the Indeed and JobSpy country vocabulary. `main.trigger_backfill_descriptions` loops over the private `_fetch_job_description`. Scrape summaries and health rules are in `scheduler.py` (`_format_scrape_summary`, `check_scrape_health`). `models/db.get_existing_external_ids` is only used by sources. `targets.now_utc` has no callers.
- **Scoring from inside the scraper.** `orchestrator`, `company_pages` and `linkedin_extension` call `analyzer.cv_scorer.analyze_unscored_jobs` themselves rather than leaving it to the caller.
