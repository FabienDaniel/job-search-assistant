"""free-work.com source: French tech and IT jobs and freelance missions, read from the public
API that the site's own pages call (API Platform, JSON-LD collections).

Each listing carries the full posting, so no job page is read. The stored URL is the Free-Work
page, a Board link. `applicationUrl` is rarely set and goes to `apply_url` when it leaves the
board. Salaries and daily rates are in euros, so they stay in the description as text, as on
caribbeanjobs.

Job type picks the contracts: Contract is freelance missions, Full-time is CDI and CDD, Part-time
sends no filter. Remote asks for fully remote jobs. Location is a city matched on the client.
"""

import httpx

from backend.analyzer.work_arrangement import HYBRID, ONSITE, REMOTE
from backend.models.db import Search
from backend.scraper._shared import job_boards
from backend.scraper._shared.html_text import html_to_text
from backend.scraper._shared.job_boards import (
    Board,
    BoardError,
    employer_apply,
    make_row,
    term_of,
    too_old,
)

_SEARCH = "https://www.free-work.com/api/job_postings"
_SITE = "https://www.free-work.com/fr/tech-it/job-mission"
_PAGE = 100
_MAX_PAGES = 10
# The API rejects `contracts[]=`. Several values go comma-separated.
_CONTRACTS = {"contract": "contractor", "fulltime": "permanent,fixed-term"}
_ARRANGEMENTS = {"full": REMOTE, "partial": HYBRID, "none": ONSITE}
# The API filters postings by request locale and answers en-US with zero results.
_HEADERS = {"Accept": "application/ld+json", "Accept-Language": "fr"}


def _pay(j: dict) -> str:
    lines = []
    if j.get("annualSalary"):
        lines.append(f"Salary: {j['annualSalary']}")
    if j.get("dailySalary"):
        lines.append(f"Daily rate: {j['dailySalary']}")
    if j.get("duration") or j.get("durationValue"):
        lines.append(
            f"Duration: {j.get('durationValue') or ''} {j.get('durationPeriod') or ''}".strip()
        )
    return "\n".join(lines)


def _row(j: dict) -> dict:
    job_slug = (j.get("job") or {}).get("slug")
    url = f"{_SITE}/{job_slug}/{j.get('slug')}" if job_slug and j.get("slug") else ""
    arrangement = _ARRANGEMENTS.get(j.get("remoteMode"))
    place = (j.get("location") or {}).get("label") or ""
    if arrangement == REMOTE:
        place = f"Remote ({place})" if place else "Remote"
    parts = [
        html_to_text(j.get(k) or "")
        for k in ("description", "candidateProfile", "companyDescription")
    ]
    description = "\n\n".join(p for p in [_pay(j), *parts] if p)
    return make_row(
        title=j.get("title"),
        company=(j.get("company") or {}).get("name") or "",
        url=url,
        location=place,
        description=description,
        arrangement=arrangement,
        posted=j.get("publishedAt"),
        ref=str(j["id"]) if j.get("id") is not None else None,
        apply_url=employer_apply(j.get("applicationUrl")),
    )


async def _list(client: httpx.AsyncClient, search: Search, limit: int) -> list:
    """Results come newest first, so paging stops at the first job older than Hours old."""
    params = {"searchKeywords": term_of(search), "order": "date", "itemsPerPage": _PAGE}
    contracts = _CONTRACTS.get(search.job_type or "")
    if contracts:
        params["contracts"] = contracts
    if search.is_remote:
        params["remoteMode"] = "full"
    rows = []
    for page in range(1, _MAX_PAGES + 1):
        resp = await client.get(
            _SEARCH,
            params=dict(params, page=page),
            headers=_HEADERS,
        )
        if resp.status_code >= 400:
            raise BoardError(f"HTTP {resp.status_code} from the Free-Work API")
        jobs = resp.json().get("hydra:member") or []
        batch = [r for r in (_row(j) for j in jobs) if r["url"]]
        fresh = [r for r in batch if not too_old(r, search.hours_old)]
        rows += fresh
        if len(jobs) < _PAGE or len(fresh) < len(batch) or len(rows) >= limit:
            break
    return rows[:limit]


BOARDS = {"freework": Board("Free-Work", _list, local_city=True)}


async def run(search: Search) -> dict:
    return await job_boards.run(search, BOARDS)


async def preview(search: Search, db) -> dict:
    return await job_boards.preview(search, db, BOARDS)
