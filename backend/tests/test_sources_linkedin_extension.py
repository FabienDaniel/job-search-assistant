"""Tests for sources/linkedin_extension.py — Voyager-API enrichment."""

import asyncio

import pytest


def test_exposes_enrich():
    from backend.scraper.sources import linkedin_extension

    assert hasattr(linkedin_extension, "enrich")


def test_enrich_is_async():
    from backend.scraper.sources import linkedin_extension

    assert asyncio.iscoroutinefunction(linkedin_extension.enrich)


@pytest.mark.asyncio
async def test_enrich_handles_empty_list(test_db):
    """Passing [] returns without raising and without any API calls."""
    from backend.scraper.sources.linkedin_extension import enrich

    result = await enrich([])
    # Result may be a dict with counts, or None — just verify no raise
    assert result is None or isinstance(result, dict)


class _FakePage:
    async def goto(self, *a, **kw):
        return None


class _FakeContext:
    async def add_cookies(self, cookies):
        return None


class _Closeable:
    async def close(self):
        return None

    async def stop(self):
        return None


def _fake_voyager(monkeypatch, jobs):
    """enrich() reads `jobs` (LinkedIn id -> job data) instead of LinkedIn."""
    from backend.scraper.sources import linkedin_extension as ext
    from backend.scraper.sources import linkedin_personal

    async def fake_browser():
        return _Closeable(), _Closeable(), _FakeContext(), _FakePage()

    async def fake_fetch(page, lid):
        return jobs.get(lid)

    async def no_h1b(job, db=None, **kw):
        return None

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(
        ext, "_load_session_cookies", lambda: [{"name": "li_at", "value": "x"}]
    )
    monkeypatch.setattr(linkedin_personal, "_get_linkedin_browser", fake_browser)
    monkeypatch.setattr(ext, "_voyager_fetch", fake_fetch)
    monkeypatch.setattr(ext, "check_job_h1b", no_h1b)
    monkeypatch.setattr(ext.asyncio, "sleep", no_sleep)


def _li_job(company):
    return {
        "title": "Product Manager",
        "company": company,
        "description": "An ordinary description.",
    }


def _imported_companies(db):
    from backend.models.db import Job

    return sorted(j.company for j in db.query(Job).all())


@pytest.mark.asyncio
async def test_import_skips_companies_on_the_global_exclude_list(test_db, monkeypatch):
    import json

    from backend.models.db import Search, Setting
    from backend.scraper.sources.linkedin_extension import enrich

    test_db.add(
        Search(
            name="Extension LI",
            search_mode="linkedin_extension",
            active=True,
            title_exclude_keywords=[],
            company_exclude=[],
            auto_scoring_depth="off",
        )
    )
    test_db.add(Setting(key="company_exclude_global", value=json.dumps(["Acme"])))
    test_db.commit()
    _fake_voyager(monkeypatch, {"1": _li_job("acme"), "2": _li_job("Globex")})

    await enrich(["1", "2"])

    assert _imported_companies(test_db) == ["Globex"]


@pytest.mark.asyncio
async def test_import_skips_active_companies_when_the_search_asks(test_db, monkeypatch):
    """ "Skip my active companies": their career pages already bring those jobs in. Aliases count."""
    from backend.models.db import Company, Search
    from backend.scraper.sources.linkedin_extension import enrich

    test_db.add(
        Search(
            name="Extension LI",
            search_mode="linkedin_extension",
            active=True,
            title_exclude_keywords=[],
            company_exclude=[],
            auto_scoring_depth="off",
            exclude_active_companies=True,
        )
    )
    test_db.add(
        Company(
            name="Acme Corporation",
            aliases=["Acme"],
            active=True,
            scrape_urls=["https://acme.example/jobs"],
        )
    )
    test_db.commit()
    _fake_voyager(monkeypatch, {"1": _li_job("Acme"), "2": _li_job("Globex")})

    await enrich(["1", "2"])

    assert _imported_companies(test_db) == ["Globex"]


@pytest.mark.asyncio
async def test_import_keeps_only_the_companies_on_the_include_list(
    test_db, monkeypatch
):
    """ "Company include · exact" keeps only those companies, any case, as on every other search."""
    from backend.models.db import Search
    from backend.scraper.sources.linkedin_extension import enrich

    test_db.add(
        Search(
            name="Extension LI",
            search_mode="linkedin_extension",
            active=True,
            title_exclude_keywords=[],
            company_exclude=[],
            auto_scoring_depth="off",
            company_filter=["Acme"],
        )
    )
    test_db.commit()
    _fake_voyager(monkeypatch, {"1": _li_job("ACME"), "2": _li_job("Globex")})

    await enrich(["1", "2"])

    assert _imported_companies(test_db) == ["ACME"]


@pytest.mark.asyncio
async def test_import_with_an_empty_include_list_keeps_every_company(
    test_db, monkeypatch
):
    from backend.models.db import Search
    from backend.scraper.sources.linkedin_extension import enrich

    test_db.add(
        Search(
            name="Extension LI",
            search_mode="linkedin_extension",
            active=True,
            title_exclude_keywords=[],
            company_exclude=[],
            auto_scoring_depth="off",
            company_filter=[],
        )
    )
    test_db.commit()
    _fake_voyager(monkeypatch, {"1": _li_job("Acme"), "2": _li_job("Globex")})

    await enrich(["1", "2"])

    assert _imported_companies(test_db) == ["Acme", "Globex"]
