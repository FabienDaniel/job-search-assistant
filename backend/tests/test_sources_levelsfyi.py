"""Tests for sources/levelsfyi.py."""
import asyncio

import pytest


def test_exposes_run_and_preview():
    from backend.scraper.sources import levelsfyi
    assert hasattr(levelsfyi, "run")
    assert hasattr(levelsfyi, "preview")


def test_run_is_async():
    from backend.scraper.sources import levelsfyi
    assert asyncio.iscoroutinefunction(levelsfyi.run)


def test_is_levelsfyi_detects_levels():
    from backend.scraper.sources.levelsfyi import _is_levelsfyi
    assert _is_levelsfyi("https://www.levels.fyi/jobs")


def test_is_levelsfyi_rejects_non_levels():
    from backend.scraper.sources.levelsfyi import _is_levelsfyi
    assert not _is_levelsfyi("https://boards.greenhouse.io/acme")


def test_levelsfyi_job_id_keeps_the_whole_alphanumeric_id():
    """Since 2026-10-09 levels.fyi ids are base-36 ("2ci7r6weraiqb"); reading only the leading
    digits stored "jobId=2", a 404 page that scoring could never parse."""
    from backend.scraper.sources.levelsfyi import _levelsfyi_job_id
    assert _levelsfyi_job_id("/jobs?jobId=2ci7r6weraiqb") == "2ci7r6weraiqb"
    assert _levelsfyi_job_id("/jobs?jobId=0748ffyywjm40&utm=x") == "0748ffyywjm40"
    assert _levelsfyi_job_id("https://www.levels.fyi/jobs?jobId=113365928120328902") == "113365928120328902"
    assert _levelsfyi_job_id("/jobs?standardJobId=abc") is None
    assert _levelsfyi_job_id("/jobs?jobId=") is None


def test_parse_levelsfyi_salary_parses_range():
    from backend.scraper.sources.levelsfyi import _parse_levelsfyi_salary
    # Return shape: (location, work_arrangement, salary_min, salary_max)
    result = _parse_levelsfyi_salary("San Francisco \u00b7 Remote \u00b7 $100K - $150K")
    assert isinstance(result, tuple)
    assert len(result) == 4
    location, work_arrangement, salary_min, salary_max = result
    assert location == "San Francisco"
    assert work_arrangement == "Remote"
    assert salary_min == 100000
    assert salary_max == 150000


@pytest.mark.asyncio
async def test_preview_needs_a_url(test_db):
    from backend.models.db import Search
    from backend.scraper.sources import levelsfyi
    with pytest.raises(ValueError, match="levels.fyi URL"):
        await levelsfyi.preview(Search(name="t", search_mode="levels_fyi"), test_db)


class _Closeable:
    async def close(self):
        return None

    async def stop(self):
        return None


def _fake_levels_page(monkeypatch, titles):
    from backend.scraper.sources import levelsfyi

    async def fake_get_browser():
        return _Closeable(), _Closeable()

    async def fake_scrape(url, browser=None, max_pages=50):
        return [{"title": t, "company": "Acme", "url": f"https://www.levels.fyi/jobs?jobId={i}"}
                for i, t in enumerate(titles, 1)]
    monkeypatch.setattr(levelsfyi, "_get_browser", fake_get_browser)
    monkeypatch.setattr(levelsfyi, "_scrape_levelsfyi", fake_scrape)


@pytest.mark.asyncio
async def test_preview_reports_the_title_filter_without_saving(test_db, monkeypatch):
    from backend.models.db import Job, Search
    from backend.scraper.sources import levelsfyi
    _fake_levels_page(monkeypatch, ["Product Manager", "Sales Intern"])
    search = Search(name="t", search_mode="levels_fyi", direct_url="https://www.levels.fyi/jobs",
                    title_exclude_keywords=["intern"])

    out = await levelsfyi.preview(search, test_db)

    assert out["raw_count"] == 2 and out["after_filter"] == 1
    assert [(j["title"], j["kept"]) for j in out["jobs"]] == [("Product Manager", True), ("Sales Intern", False)]
    assert out["jobs"][1]["reason"] == "Excluded by: intern"
    assert test_db.query(Job).count() == 0


@pytest.mark.asyncio
async def test_preview_drops_titles_on_the_global_exclude_list_like_the_run(test_db, monkeypatch):
    import json
    from backend.models.db import Search, Setting
    from backend.scraper.sources import levelsfyi
    test_db.add(Setting(key="title_exclude_global", value=json.dumps(["staff"])))
    test_db.commit()
    _fake_levels_page(monkeypatch, ["Product Manager", "Staff Product Manager"])
    search = Search(name="t", search_mode="levels_fyi", direct_url="https://www.levels.fyi/jobs")

    out = await levelsfyi.preview(search, test_db)

    assert [(j["title"], j["kept"]) for j in out["jobs"]] == [("Product Manager", True),
                                                              ("Staff Product Manager", False)]
    assert out["jobs"][1]["reason"] == "Excluded by: staff"
