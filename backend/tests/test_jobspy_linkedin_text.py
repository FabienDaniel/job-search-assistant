"""JobSpy's LinkedIn rows come without a description; new ones get it from LinkedIn's public
job page before they are stored (body exclusion and scoring need the text)."""

import asyncio

import pandas as pd

from backend.scraper._shared.dedup import make_external_id
from backend.scraper.sources import jobspy

LONG = "Design distributed systems for payments. " * 20


def _df():
    return pd.DataFrame(
        [
            {
                "site": "linkedin",
                "company": "Acme",
                "title": "Engineer",
                "job_url": "https://www.linkedin.com/jobs/view/1",
                "description": None,
            },
            {
                "site": "linkedin",
                "company": "Acme",
                "title": "Old role",
                "job_url": "https://www.linkedin.com/jobs/view/2",
                "description": None,
            },
            {
                "site": "indeed",
                "company": "Beta",
                "title": "Engineer",
                "job_url": "https://www.indeed.com/viewjob?jk=3",
                "description": None,
            },
        ]
    )


def test_new_linkedin_rows_get_the_listing_text(monkeypatch):
    calls = []

    async def fake_fetch(url, job=None):
        calls.append(url)
        return LONG

    monkeypatch.setattr(
        "backend.scraper.ats._descriptions._fetch_job_description", fake_fetch
    )
    monkeypatch.setattr(
        "backend.scraper._shared.employer_text.asyncio.sleep",
        lambda s: asyncio.sleep(0),
    )
    df = _df()
    existing = {
        make_external_id("Acme", "Old role", "https://www.linkedin.com/jobs/view/2")
    }
    loop = asyncio.new_event_loop()
    try:
        n = jobspy._fill_linkedin_descriptions(df, existing, loop)
    finally:
        loop.close()
    assert n == 1
    assert calls == [
        "https://www.linkedin.com/jobs/view/1"
    ]  # not the stored one, not Indeed
    assert df.iloc[0]["description"] == LONG
    assert df.iloc[1]["description"] is None


class _Page:
    status_code = 200

    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


def test_the_linkedin_fetch_keeps_the_description_html(monkeypatch):
    import backend.scraper._shared.url_safety as us
    from backend.scraper.ats import _descriptions
    from backend.tests.test_reader_view import _GUEST_PAGE

    async def fake_get(url, **kw):
        return _Page(_GUEST_PAGE)

    monkeypatch.setattr(us, "safe_get", fake_get)
    monkeypatch.setattr(us, "assert_public_http_url", lambda url: None)
    job = {"url": "https://www.linkedin.com/jobs/view/1"}
    asyncio.run(_descriptions._fetch_job_description(job["url"], job=job))
    html = job["description_html"]
    assert "<strong>Seniority level</strong> Mid-Senior level" in html
    assert "<li> un Chef de Projet Data ; </li>" in html
    assert "Show more" not in html and "Découvrez comment" not in html


def test_the_description_html_reaches_the_row(monkeypatch):
    async def fake_fetch(url, job=None):
        job["description_html"] = "<p>formatted</p>"
        return LONG

    monkeypatch.setattr(
        "backend.scraper.ats._descriptions._fetch_job_description", fake_fetch
    )
    monkeypatch.setattr(
        "backend.scraper._shared.employer_text.asyncio.sleep",
        lambda s: asyncio.sleep(0),
    )
    df = _df()
    existing = {
        make_external_id("Acme", "Old role", "https://www.linkedin.com/jobs/view/2")
    }
    loop = asyncio.new_event_loop()
    try:
        jobspy._fill_linkedin_descriptions(df, existing, loop)
    finally:
        loop.close()
    assert df.iloc[0]["description_html"] == "<p>formatted</p>"
    assert df.iloc[2]["description_html"] is None  # Indeed: not fetched
