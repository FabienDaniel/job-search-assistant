"""The company "Test scrape" must route a jobs.uber.com URL to the Uber handler,
the same one the real scrape uses, not fall through to the generic reader."""

import pytest

from backend.models.db import Company

URL = "https://jobs.uber.com/en/jobs/?team=Product&location=San%20Francisco"


@pytest.fixture
def _fake_uber(monkeypatch):
    import backend.scraper._shared.browser as browser_mod
    import backend.scraper.ats.uber as uber

    class _FakeBrowser:
        async def close(self):
            return None

    class _FakePw:
        async def stop(self):
            return None

    async def fake_get_browser():
        return _FakePw(), _FakeBrowser()

    async def no_page(browser):  # the generic reader opens a page. Uber must not.
        raise AssertionError("jobs.uber.com URL fell through to the generic reader")

    calls = []

    async def fake_scrape(url, debug=False, **kw):
        calls.append((url, debug))
        return [
            {
                "title": "Senior Product Manager",
                "url": "https://jobs.uber.com/en/jobs/160013/",
            }
        ], []

    monkeypatch.setattr(browser_mod, "_get_browser", fake_get_browser)
    monkeypatch.setattr(browser_mod, "_new_page", no_page)
    monkeypatch.setattr(uber, "scrape", fake_scrape)
    return calls


@pytest.mark.asyncio
async def test_uber_url_is_read_by_the_uber_handler(test_db, _fake_uber):
    from backend.api.routes_companies import test_scrape_company

    c = Company(
        name="ZZ Uber",
        active=True,
        scrape_urls=[URL],
        title_include_expr="manager",
        title_exclude_keywords=[],
    )
    test_db.add(c)
    test_db.commit()

    out = await test_scrape_company(str(c.id), db=test_db)

    assert _fake_uber == [(URL, True)]
    assert [j["title"] for j in out["jobs"]] == ["Senior Product Manager"]
    assert out["jobs"][0]["kept"] is True
    assert any("Uber API" in line for line in out["urls_scraped"])
