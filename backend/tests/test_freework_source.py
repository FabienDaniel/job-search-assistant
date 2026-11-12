"""Free-Work source: the API client, its rows, link kinds and the mode wiring (no network)."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest

from backend.models.db import Job, Search
from backend.scraper import search_modes as M
from backend.scraper._shared import job_boards
from backend.scraper.sources import freework


def _search(**kw):
    base = dict(
        name="t",
        search_mode="freework",
        search_term="python",
        location="",
        is_remote=None,
        job_type="fulltime",
        hours_old=0,
        results_wanted=10,
        sources=[],
        company_filter=[],
    )
    base.update(kw)
    return SimpleNamespace(**base)


class FakeSite:
    def __init__(self):
        self.requests = []
        self.pages = {}  # page -> postings

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        page = int(request.url.params.get("page", "1"))
        jobs = self.pages.get(page, [])
        return httpx.Response(
            200, json={"hydra:totalItems": len(jobs), "hydra:member": jobs}
        )


@pytest.fixture
def sites(monkeypatch):
    fake = FakeSite()
    monkeypatch.setattr(
        job_boards,
        "http_client",
        lambda mounts=None: httpx.AsyncClient(
            transport=httpx.MockTransport(fake), follow_redirects=True
        ),
    )
    return fake


def _fw(i, days_old=1, remote="partial", **kw):
    published = datetime.now(timezone.utc) - timedelta(days=days_old)
    j = {
        "id": 1000 + i,
        "title": f"Développeur Python {i}",
        "slug": f"developpeur-python-{i}",
        "job": {"slug": "developpeur-python"},
        "company": {"name": "Acme"},
        "location": {"label": "Paris, Île-de-France"},
        "remoteMode": remote,
        "description": "<p>Build <b>APIs</b></p>",
        "candidateProfile": "<p>5 ans de Python</p>",
        "companyDescription": None,
        "annualSalary": None,
        "dailySalary": "500-600 €",
        "duration": None,
        "durationValue": 6,
        "durationPeriod": "month",
        "applicationUrl": None,
        "publishedAt": published.isoformat(),
    }
    j.update(kw)
    return j


@pytest.mark.parametrize(
    "job_type,contracts",
    [
        ("contract", "contractor"),
        ("fulltime", "permanent,fixed-term"),
        ("parttime", None),
    ],
)
@pytest.mark.asyncio
async def test_freework_maps_job_type_to_contracts(sites, job_type, contracts):
    sites.pages = {1: [_fw(1)]}
    async with job_boards.http_client() as c:
        await freework._list(c, _search(job_type=job_type), 10)
    params = sites.requests[0].url.params
    assert params.get("contracts") == contracts
    assert params["searchKeywords"] == "python" and params["order"] == "date"
    assert "remoteMode" not in params
    assert sites.requests[0].headers["accept"] == "application/ld+json"
    assert sites.requests[0].headers["accept-language"] == "fr"


@pytest.mark.asyncio
async def test_freework_remote_asks_for_full_remote(sites):
    sites.pages = {1: [_fw(1, remote="full")]}
    async with job_boards.http_client() as c:
        rows = await freework._list(c, _search(is_remote=True), 10)
    assert sites.requests[0].url.params["remoteMode"] == "full"
    assert rows[0]["location"] == "Remote (Paris, Île-de-France)"


@pytest.mark.asyncio
async def test_freework_paging_stops_at_old_jobs(sites, monkeypatch):
    monkeypatch.setattr(freework, "_PAGE", 3)
    sites.pages = {
        1: [_fw(1), _fw(2), _fw(3)],
        2: [_fw(4), _fw(99, days_old=30), _fw(5)],
        3: [_fw(6)],
    }
    async with job_boards.http_client() as c:
        rows = await freework._list(c, _search(hours_old=168), 100)
    assert [r["ref"] for r in rows] == ["1001", "1002", "1003", "1004", "1005"]
    assert len(sites.requests) == 2


@pytest.mark.asyncio
async def test_freework_paging_stops_at_a_short_page(sites):
    sites.pages = {1: [_fw(1), _fw(2)], 2: [_fw(3)]}
    async with job_boards.http_client() as c:
        rows = await freework._list(c, _search(), 100)
    assert len(rows) == 2 and len(sites.requests) == 1


def test_freework_row():
    r = freework._row(_fw(7))
    assert r["url"] == (
        "https://www.free-work.com/fr/tech-it/job-mission/developpeur-python/developpeur-python-7"
    )
    assert (r["company"], r["location"], r["arrangement"]) == (
        "Acme",
        "Paris, Île-de-France",
        "hybrid",
    )
    assert "Daily rate: 500-600 €" in r["description"]
    assert "Duration: 6 month" in r["description"]
    assert "Build APIs" in r["description"] and "5 ans de Python" in r["description"]
    assert r["salary_min"] is None and r["apply_url"] is None


def test_freework_row_without_a_job_slug_has_no_url():
    assert freework._row(_fw(1, job=None))["url"] == ""


@pytest.mark.parametrize(
    "apply_link,kind",
    [
        (None, "board"),
        ("https://jobs.lever.co/acme/1", "direct"),
    ],
)
@pytest.mark.asyncio
async def test_freework_link_kinds(sites, test_db, monkeypatch, apply_link, kind):
    async def fake_analyze(job, db=None, arrangement=None):
        job.work_arrangement = arrangement

    monkeypatch.setattr(job_boards, "analyze_inline", fake_analyze)
    monkeypatch.setattr("backend.activity.log_activity", lambda *a, **k: None)
    sites.pages = {1: [_fw(1, applicationUrl=apply_link)]}
    search = Search(
        name="t",
        search_mode="freework",
        search_term="python",
        job_type="contract",
        results_wanted=10,
        hours_old=0,
        company_exclude=[],
    )
    test_db.add(search)
    test_db.commit()
    res = await freework.run(search)
    assert res["error"] is None and res["source_breakdown"]["freework"]["new"] == 1
    test_db.expire_all()
    job = test_db.query(Job).one()
    assert (job.source, job.link_kind, job.apply_url) == ("freework", kind, apply_link)
    assert job.url.startswith("https://www.free-work.com/")


def test_config_error_needs_a_term():
    assert (
        M.config_error(Search(search_mode="freework"))
        == "Free-Work needs a search term before it can run"
    )
    assert M.config_error(Search(search_mode="freework", search_term="python")) is None
