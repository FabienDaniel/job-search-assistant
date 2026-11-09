"""Search config CRUD endpoints."""

import asyncio
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.countries import (
    DEFAULT_COUNTRY,
    normalize_country,
    split_country_suffix,
    supported_countries,
)
from backend.models.db import Job, ScrapeLog, Search, get_db, is_acknowledged
from backend.scraper import search_modes as _modes

logger = logging.getLogger("jobnavigator.routes_searches")

# What each mode is lives in backend/scraper/search_modes.py (R30 I-02). The two seeded
# browser-extension searches ("Extension"/"Extension LI") have no scraper and must not be
# deleted — jobs arrive by push; PATCH stays open for the editor's filters.
EXTENSION_MODES = _modes.EXTENSION_MODES

router = APIRouter(prefix="/searches", tags=["searches"])

# In-memory store for async test results, each tagged with the account that started it
# (MT-4): run_id -> {"status": "running"|"done", "result": ..., "account": "<uuid>"}.
_test_results: dict[str, dict] = {}


# One background Test in flight per search and account (R30 S-07). An Apify Test is a paid
# run (one actor run per board), and the dashboard's confirm dialog is no guard against a
# double click, a second tab or a scripted client. Keyed like a job_monitor run
# ("search_test:<search id>", plus "@<account>" for a member, so another account's Test of
# its own search never blocks this one); the value is the Test's run_id.
_tests_in_flight: dict[str, str] = {}


def _test_flight_key(search_id) -> str:
    from backend.job_monitor import _make_key, _run_account

    return _make_key("search_test", str(search_id), _run_account("search_test"))


def _account_key() -> Optional[str]:
    from backend.accounts.context import current_account

    acc = current_account.get()
    return str(acc) if acc is not None else None


class SearchCreate(BaseModel):
    name: str
    active: bool = True
    # None = the mode's default (JobSpy's four boards, both LinkedIn collections, else none).
    sources: Optional[list] = None
    search_mode: str = "keyword"
    search_term: Optional[str] = None
    direct_url: Optional[str] = None
    location: str = ""
    country: str = DEFAULT_COUNTRY
    is_remote: Optional[bool] = None
    job_type: str = "fulltime"
    # Optional so the editor can clear the field: an explicit null falls back to
    # the column default on insert (SQLAlchemy applies it for a None value).
    hours_old: Optional[int] = 24
    results_wanted: Optional[int] = 50
    title_include_keywords: list = []
    title_exclude_keywords: list = ["intern", "junior", "associate"]
    company_filter: list = []
    company_exclude: list = []
    exclude_active_companies: bool = False
    max_pages: int = 50
    min_fit_score: int = 0
    require_salary: bool = False
    run_interval_minutes: int = 0
    auto_scoring_depth: str = "off"


@router.get("")
def list_searches(db: Session = Depends(get_db)):
    searches = db.query(Search).order_by(Search.created_at).all()
    # Latest ScrapeLog per search → surface the most recent run's outcome so the
    # UI can show a live summary/health line (mirrors what /companies does).
    from sqlalchemy import and_, func

    from backend.models.db import ScrapeLog

    latest_sub = (
        db.query(ScrapeLog.search_id, func.max(ScrapeLog.ran_at).label("mx"))
        .filter(ScrapeLog.search_id.isnot(None))
        .group_by(ScrapeLog.search_id)
        .subquery()
    )
    last_log = {
        str(l.search_id): l
        for l in db.query(ScrapeLog)
        .join(
            latest_sub,
            and_(
                ScrapeLog.search_id == latest_sub.c.search_id,
                ScrapeLog.ran_at == latest_sub.c.mx,
            ),
        )
        .all()
    }
    rates = _direct_rates(db)
    out = []
    for s in searches:
        row = _search_to_dict(s, last_log.get(str(s.id)))
        row["direct_rate"] = rates.get(s.id)
        out.append(row)
    return out


def _direct_rates(db) -> dict:
    """{search id: {"direct": n, "total": n}}: how many of each search's jobs of the last 90 days
    (filtered ones left out) can be applied to directly: the employer's link, or Easy Apply."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import case, func

    from backend.models.db import Job

    since = datetime.now(timezone.utc) - timedelta(days=90)
    rows = (
        db.query(
            Job.search_id,
            func.count(Job.id),
            func.sum(case((Job.link_kind.in_(("direct", "easy_apply")), 1), else_=0)),
        )
        .filter(
            Job.search_id.isnot(None),
            Job.status != "ignored",
            Job.discovered_at >= since,
        )
        .group_by(Job.search_id)
        .all()
    )
    return {
        sid: {"direct": int(direct or 0), "total": int(total)}
        for sid, total, direct in rows
        if total
    }


@router.get("/countries")
def list_countries():
    """The countries Indeed supports, straight from the installed jobspy library, so the search form offers exactly what the scraper accepts."""
    return [{"value": value, "label": label} for value, label in supported_countries()]


@router.get("/apify-boards")
def list_apify_boards():
    """The boards an Apify search can pick, in PRESETS order; the first one is the default for a new search.
    `price_per_1k` (USD, Free plan) and `test_max_usd` (the spend cap a Test run of that board is
    started with) let the Test button name the cost before a paid preview; `max_results` is the
    per-board cap on Results wanted."""
    from backend.scraper.sources.apify import (
        MAX_RESULTS,
        PRESETS,
        PREVIEW_LIMIT,
        charge_cap_usd,
    )

    return [
        {
            "value": key,
            "label": p.label,
            "hint": p.hint,
            "actor": p.actor,
            "price_per_1k": p.price_per_1k,
            "test_max_usd": charge_cap_usd(p, PREVIEW_LIMIT),
            "preview_limit": PREVIEW_LIMIT,
            "max_results": MAX_RESULTS,
        }
        for key, p in PRESETS.items()
    ]


def _writable_mode(key) -> "_modes.SearchMode":
    """The mode a client may create or switch a search to, or 400: a known mode that has a
    scraper. The extension modes belong to the two seeded searches only (R30 P0-02)."""
    mode = _modes.get_mode(key)
    if mode is None:
        known = ", ".join(k for k, m in _modes.SEARCH_MODES.items() if not m.extension)
        raise HTTPException(
            status_code=400, detail=f"Unknown search mode {key!r}; one of: {known}"
        )
    if mode.extension:
        raise HTTPException(
            status_code=400,
            detail=f"{mode.label} searches are built in; they cannot be created or switched to",
        )
    return mode


def _sources_for(key, sources) -> list:
    """`sources` as stored for this mode, or 400: its default when None, checked against the
    mode's board list, and [] for a mode that takes none (R30 P0-03). Apify's own check is
    `_apify_sources`."""
    mode = _modes.get_mode(key)
    if mode is not None and mode.boards == "apify":
        return sources if sources is not None else []
    if mode is None or mode.boards is None:
        return []
    if sources is None:
        return _modes.default_sources(key)
    error = _modes.bad_sources(key, sources)
    if error:
        raise HTTPException(status_code=400, detail=error)
    return list(sources)


def _apify_sources(sources) -> list:
    """The boards of an Apify search, or 400: a non-empty list of Apify board keys only.

    The JobSpy default list (SearchCreate.sources) or a keyword search patched to
    `apify` would otherwise reach the paid source with boards nobody picked."""
    from backend.scraper.sources.apify import PRESETS

    sources = sources if isinstance(sources, list) else []
    unknown = [s for s in sources if s not in PRESETS]
    if not sources or unknown:
        raise HTTPException(
            status_code=400,
            detail="An Apify search needs at least one Apify board from GET /api/searches/apify-boards"
            + (
                f"; not Apify boards: {', '.join(map(str, unknown))}" if unknown else ""
            ),
        )
    return sources


def _validated_country(value) -> str:
    """The stored form of a country name, or 400. An unknown name would otherwise reach jobspy and raise mid-scrape."""
    name = normalize_country(value)
    if not name:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown country '{value}' — pick one from GET /api/searches/countries",
        )
    return name


def _validated_location(location, country) -> str:
    """The location text, or 400 when its own country segment names another country.

    The scraper appends the label of `country` to `location`, so the pair must
    agree. It used to fail loudly when it did not: Indeed answered a Canadian
    city on the US site with zero rows. Composed, the same pair becomes a silent
    wrong-country scrape — "Canada" with country "usa" would query "United
    States" and store US rows. The write path refuses the pair instead of
    choosing one side for the user.
    """
    named = split_country_suffix(location)[1]
    if named and named != country:
        raise HTTPException(
            status_code=400,
            detail=f"Location '{location}' names {named}, but Country is {country} "
            f"— leave the country out of Location, or change Country",
        )
    return location


@router.post("")
def create_search(data: SearchCreate, db: Session = Depends(get_db)):
    payload = data.model_dump()
    mode = _writable_mode(payload.get("search_mode") or "keyword")
    payload["search_mode"] = mode.key
    payload["country"] = _validated_country(payload["country"])
    # Only the modes that send location with country to the board (JobSpy, Apify) check the
    # pair; for the URL-driven modes country means nothing and must not reject a row.
    if mode.uses_country:
        payload["location"] = _validated_location(
            payload["location"], payload["country"]
        )
    payload["sources"] = _sources_for(mode.key, payload.get("sources"))
    if mode.boards == "apify":
        from backend.scraper.sources.apify import clamp_results

        payload["sources"] = _apify_sources(payload.get("sources"))
        if payload.get("results_wanted") is not None:
            payload["results_wanted"] = clamp_results(payload["results_wanted"])
    if mode.paid and "active" not in data.model_fields_set:
        # A paid source starts paused unless the client asked for an active search, so
        # nothing bills before the user has looked at the boards and Results wanted.
        payload["active"] = False
    search = Search(**payload)
    db.add(search)
    db.commit()
    return _search_to_dict(search)


@router.get("/clone-sources")
def search_clone_sources(db: Session = Depends(get_db)):
    """Other accounts' searches for the "Copy from…" picker: `{accounts: [{id, name, color, role, items: [{id, name, search_mode, search_term, direct_url, location, country, active}]}]}`. Empty `accounts` with a single account; never the caller's own rows; built-in extension searches left out."""
    from backend.accounts import admin

    return admin.search_clone_sources(db)


@router.post("/clone")
def clone_search(body: dict, db: Session = Depends(get_db)):
    """Copy one search of another account (`{source_id}`) into this account, due at once. A name clash becomes "<name> (copy)" / "(copy 2)". 409 `needs_two_accounts` / `builtin_search`, 404 `source_not_found` for an own or unknown id."""
    from backend.accounts import admin

    try:
        new_id = admin.clone_search(db, (body or {}).get("source_id"))
    except admin.CloneError as e:
        return JSONResponse(
            status_code=e.status, content={"detail": e.code, "message": e.message}
        )
    search = db.query(Search).filter(Search.id == new_id).first()
    return _search_to_dict(search)


@router.patch("/{search_id}")
def update_search(search_id: str, updates: dict, db: Session = Depends(get_db)):
    search = db.query(Search).filter(Search.id == search_id).first()
    if not search:
        raise HTTPException(status_code=404, detail="Search not found")

    allowed = {
        "name",
        "active",
        "sources",
        "search_mode",
        "search_term",
        "direct_url",
        "location",
        "country",
        "is_remote",
        "job_type",
        "hours_old",
        "results_wanted",
        "title_include_keywords",
        "title_exclude_keywords",
        "company_filter",
        "company_exclude",
        "exclude_active_companies",
        "max_pages",
        "min_fit_score",
        "require_salary",
        "auto_scoring_depth",
        "run_interval_minutes",
    }
    if "country" in updates:
        updates["country"] = _validated_country(updates["country"])
    current = _modes.get_mode(search.search_mode)
    if "search_mode" in updates:
        wanted = updates["search_mode"] or "keyword"
        if current is not None and current.extension and wanted != search.search_mode:
            raise HTTPException(
                status_code=400, detail="A built-in extension search keeps its mode"
            )
        if wanted != search.search_mode:
            updates["search_mode"] = _writable_mode(wanted).key
    mode = _modes.get_mode(updates.get("search_mode", search.search_mode)) or current
    switching_mode = (
        updates.get("search_mode", search.search_mode) != search.search_mode
    )
    # A mode switch resets `sources` to the new mode's default unless the patch sets them:
    # Apify boards must not reach JobSpy, nor JobSpy's boards a mode that takes none (R30 I-03).
    if (
        mode is not None
        and mode.boards != "apify"
        and ("sources" in updates or switching_mode)
    ):
        updates["sources"] = _sources_for(mode.key, updates.get("sources"))
    # The pair is validated, not one field: a patch may carry either one, and the
    # other keeps its stored value. This runs before the writes, so a rejected
    # patch leaves the row alone.
    if (
        mode is not None
        and mode.uses_country
        and ("location" in updates or "country" in updates)
    ):
        _validated_location(
            updates.get("location", search.location),
            updates.get("country", search.country) or DEFAULT_COUNTRY,
        )
    if mode is not None and mode.boards == "apify":
        from backend.scraper.sources.apify import clamp_results

        switching = search.search_mode != mode.key
        if switching or "sources" in updates:
            updates["sources"] = _apify_sources(updates.get("sources", search.sources))
        if switching or "results_wanted" in updates:
            rw = updates.get("results_wanted", search.results_wanted)
            if rw is not None:
                updates["results_wanted"] = clamp_results(rw)
        # Switching an existing search to the paid source pauses it too, unless the
        # patch sets `active` itself (same rule as a new Apify search).
        if switching and "active" not in updates:
            updates["active"] = False
    for key, value in updates.items():
        if key in allowed:
            setattr(search, key, value)
    db.commit()
    return _search_to_dict(search)


@router.post("/{search_id}/acknowledge")
def acknowledge_search_warning(search_id: str, db: Session = Depends(get_db)):
    """Mark this search's current scrape warning as seen so /api/health/entities stops counting it until a newer ScrapeLog row appears (muted, not hidden); the two seeded extension searches never scrape, so acknowledging one returns 409, the same guard /run and DELETE use."""
    search = db.query(Search).filter(Search.id == search_id).first()
    if not search:
        raise HTTPException(status_code=404, detail="Search not found")
    if search.search_mode in EXTENSION_MODES:
        raise HTTPException(
            status_code=409,
            detail="Extension searches have no scrape health to acknowledge — "
            "jobs arrive from the browser extension",
        )
    from datetime import datetime, timezone

    search.warning_acknowledged_at = datetime.now(timezone.utc)
    db.commit()
    return {
        "id": str(search.id),
        "name": search.name,
        "warning_acknowledged_at": search.warning_acknowledged_at.isoformat(),
    }


@router.delete("/{search_id}")
def delete_search(search_id: str, db: Session = Depends(get_db)):
    search = db.query(Search).filter(Search.id == search_id).first()
    if not search:
        raise HTTPException(status_code=404, detail="Search not found")
    if search.search_mode in EXTENSION_MODES:
        raise HTTPException(
            status_code=409,
            detail="Built-in extension searches cannot be deleted — "
            "pause it instead to stop importing captured jobs",
        )
    # ScrapeLog.search_id and Job.search_id are plain FKs with no ON DELETE in the
    # live schema, so orphan both instead of deleting them — jobs keep their own company/title, and run history stays readable.
    db.query(ScrapeLog).filter(ScrapeLog.search_id == search.id).update(
        {"search_id": None}, synchronize_session=False
    )
    db.query(Job).filter(Job.search_id == search.id).update(
        {"search_id": None}, synchronize_session=False
    )
    db.delete(search)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        logger.error(f"delete_search({search_id}) blocked by a foreign key: {e}")
        raise HTTPException(
            status_code=409,
            detail="Could not delete this search — another record still references it",
        ) from e
    return {"deleted": True}


@router.post("/{search_id}/run", status_code=202)
async def trigger_search(
    search_id: str, auto_score: bool = None, db: Session = Depends(get_db)
):
    """Trigger a single search in the background; returns immediately with a run_id pollable via /api/monitor/active (scope_key = search id); auto_score overrides the search's auto_scoring_depth when set."""
    search = db.query(Search).filter(Search.id == search_id).first()
    if not search:
        raise HTTPException(status_code=404, detail="Search not found")
    if search.search_mode in EXTENSION_MODES:
        raise HTTPException(
            status_code=409,
            detail="Extension searches have no scraper to run — "
            "jobs arrive from the browser extension",
        )
    # A keyword source with no term or URL would run, find nothing, and leave the run history
    # at "nothing ran"; say why up front instead.
    from backend.scraper.orchestrator import search_config_error

    config_error = search_config_error(search)
    if config_error:
        raise HTTPException(status_code=409, detail=config_error)
    if getattr(
        _modes.get_mode(search.search_mode), "paid", False
    ) and _tests_in_flight.get(_test_flight_key(search.id)):
        # A paid Test of this search is still running; a run now would buy the same
        # results a second time (R30 S-07).
        return JSONResponse(
            status_code=409,
            content={
                "detail": "test_running",
                "message": f"A Test of “{search.name}” is still running; run it when the Test finishes",
            },
        )
    search_name = search.name

    async def _do():
        from backend.scraper.orchestrator import _run_search_by_id as run_single_search

        result = await run_single_search(search_id, auto_score=auto_score)
        # Never forward scraper exception strings to the client (py/stack-trace-exposure);
        # the real text is already persisted on the ScrapeLog row and logged here.
        if isinstance(result, dict) and result.get("error"):
            logger.warning(
                "Search %s finished with scrape error: %s",
                search_id,
                result.get("error"),
            )
        # Returned string becomes JobRun.result_summary (Stats -> Run history), built
        # from the ScrapeLog row the run just wrote so the line and audit row always agree.
        from backend.scraper.orchestrator import summarize_search_run

        return summarize_search_run(search_name, result)

    from backend.job_monitor import (
        JobAlreadyRunningError,
        launch_background,
        scheduled_scrape_conflict_response,
    )

    try:
        run_id = launch_background(
            "search_run",
            _do,
            trigger="manual",
            scope_key=search_id,
            meta={"search": search_name},
        )
        return {
            "run_id": run_id,
            "status": "running",
            "search_id": search_id,
            "search": search_name,
        }
    except JobAlreadyRunningError as e:
        logger.info("Search run rejected for %s: %s", search_id, e)
        # QA F6 / R4-01: `scheduled_scrape_running` while the scheduled scrape is live.
        return scheduled_scrape_conflict_response(e)


@router.post("/{search_id}/test")
async def test_search(search_id: str, db: Session = Depends(get_db)):
    """Run a search test: keyword mode runs synchronously and returns results directly, while modes with `background_test` (search_modes.py) launch in the background and return a run_id to poll."""
    search = db.query(Search).filter(Search.id == search_id).first()
    if not search:
        raise HTTPException(status_code=404, detail="Search not found")

    mode = _modes.get_mode(search.search_mode)
    if mode is not None and mode.background_test:
        flight_key = _test_flight_key(search.id)
        in_flight = _tests_in_flight.get(flight_key)
        if in_flight:
            # The same search's Test is still running: hand back its run_id to poll instead
            # of starting another (for Apify, another paid run).
            return JSONResponse(
                status_code=409,
                content={
                    "detail": "test_running",
                    "run_id": in_flight,
                    "message": f"A Test of “{search.name}” is already running",
                },
            )
        if mode.paid:
            from backend.job_monitor import is_running

            if is_running("search_run", search_id) or is_running(
                "search_run", str(search.id)
            ):
                return JSONResponse(
                    status_code=409,
                    content={
                        "detail": "search_running",
                        "message": f"“{search.name}” is running now; test it when the run finishes",
                    },
                )
        run_id = str(uuid.uuid4())[:8]
        account = _account_key()

        def _store(status, result):
            _test_results[run_id] = {
                "status": status,
                "result": result,
                "account": account,
            }

        _store("running", None)
        _tests_in_flight[flight_key] = run_id

        # Snapshot search fields needed by the test functions (DB session won't survive across await)
        from backend.models.db import SessionLocal

        async def _run_test():
            test_db = SessionLocal()
            try:
                test_search_obj = (
                    test_db.query(Search).filter(Search.id == search_id).first()
                )
                if not test_search_obj:
                    _store("done", {"error": "Search not found"})
                    return
                import importlib

                source = importlib.import_module(
                    f"backend.scraper.sources.{mode.module}"
                )
                result = await source.preview(test_search_obj, test_db)
                _store("done", result)
            except Exception as e:
                logger.error(f"Test run {run_id} failed: {e}")
                _store("done", {"error": str(e)})
            finally:
                if _tests_in_flight.get(flight_key) == run_id:
                    _tests_in_flight.pop(flight_key, None)
                test_db.close()

        # QA F4 / R1-08: the browser's owner unlock does not ride along into the task.
        from backend.accounts.context import owner_unlocked

        async def _run_test_locked():
            with owner_unlocked(False):
                await _run_test()

        asyncio.create_task(_run_test_locked())
        return JSONResponse(
            status_code=202, content={"run_id": run_id, "status": "running"}
        )

    if mode is None or mode.key != "keyword":
        raise HTTPException(
            status_code=400,
            detail="Test is not available for "
            + (
                f"{mode.label} searches"
                if mode
                else f"search mode {search.search_mode!r}"
            ),
        )

    from backend.scraper.sources import jobspy

    try:
        return await jobspy.preview(search, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/test-result/{run_id}")
async def get_test_result(run_id: str):
    """Poll for async test results. Returns 200 with result when done, 202 while running."""
    entry = _test_results.get(run_id)
    # Another account's run (or an untagged entry) is answered exactly like an unknown id.
    if not entry or entry.get("account") != _account_key():
        raise HTTPException(status_code=404, detail="Test run not found")
    if entry["status"] == "running":
        return JSONResponse(
            status_code=202, content={"run_id": run_id, "status": "running"}
        )
    result = entry["result"]
    if len(_test_results) > 20:
        oldest = list(_test_results.keys())[: len(_test_results) - 20]
        for k in oldest:
            _test_results.pop(k, None)
    return result


def _last_source_errors(last_log) -> list:
    """Per-board failures from a search's most recent ScrapeLog row."""
    if last_log is None:
        return []
    from backend.scraper.orchestrator import source_errors, source_label

    return [
        {"source": key, "label": source_label(key), "error": err}
        for key, err in source_errors(getattr(last_log, "source_breakdown", None))
    ]


def _search_to_dict(s: Search, last_log=None) -> dict:
    return {
        "id": str(s.id),
        "name": s.name,
        "active": s.active,
        "sources": s.sources,
        "search_mode": s.search_mode,
        "search_term": s.search_term,
        "direct_url": s.direct_url,
        "location": s.location,
        "country": s.country,
        "is_remote": s.is_remote,
        "job_type": s.job_type,
        "hours_old": s.hours_old,
        "results_wanted": s.results_wanted,
        "title_include_keywords": s.title_include_keywords,
        "title_exclude_keywords": s.title_exclude_keywords,
        "company_filter": s.company_filter,
        "company_exclude": s.company_exclude,
        "exclude_active_companies": bool(s.exclude_active_companies),
        "max_pages": s.max_pages,
        "min_fit_score": s.min_fit_score,
        "require_salary": s.require_salary,
        "auto_scoring_depth": s.auto_scoring_depth,
        "run_interval_minutes": s.run_interval_minutes,
        "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
        "warning_acknowledged_at": s.warning_acknowledged_at.isoformat()
        if s.warning_acknowledged_at
        else None,
        # True while the acknowledgement still covers the newest run — the UI
        # mutes the warning instead of hiding it, so the history stays readable.
        "warning_acknowledged": is_acknowledged(
            getattr(last_log, "ran_at", None), s.warning_acknowledged_at
        ),
        "created_at": s.created_at.isoformat() if s.created_at else None,
        # most recent ScrapeLog for this search (None until it has run once)
        "last_error": (last_log.error if last_log else None),
        "last_run_warning": (bool(last_log.is_warning) if last_log else False),
        # Boards that hard-failed on the last run, e.g.
        # [{"source": "zip_recruiter", "label": "ZipRecruiter", "error": "403"}]
        "last_source_errors": _last_source_errors(last_log),
        "last_jobs_found": (last_log.jobs_found if last_log else None),
        "last_new_jobs": (last_log.new_jobs if last_log else None),
        "last_duration": (last_log.duration_seconds if last_log else None),
    }
