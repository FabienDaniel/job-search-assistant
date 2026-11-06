"""A job's posting page, fetched and kept as clean HTML and text on the job.

The feed's reader view shows `cached_page_html`. Scoring and tailoring fall back to
`cached_page_text` when a job has no description. A plain HTTP fetch is tried first.
Pages too thin to be the posting (SPAs such as Meta or Apple) are rendered with Playwright.
A bot-protection page is never stored: its text would pass as the job description.
"""
import logging

from backend.models.db import Job, SessionLocal
from backend.scraper._shared.bot_wall import is_bot_wall

logger = logging.getLogger("jobnavigator.scraper.page_cache")

_BOT_WALL_ERROR = "blocked by bot protection"


def _extract_clean_content(raw_html: str) -> tuple:
    """Extract clean, readable HTML from raw page. Returns (clean_html, plain_text)."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(raw_html, "html.parser")

    for tag in soup.find_all([
        "script", "style", "nav", "footer", "header", "noscript",
        "iframe", "svg", "img", "video", "audio", "picture", "source",
        "form", "input", "button", "select", "textarea", "label",
        "figure", "figcaption", "canvas", "map", "area",
    ]):
        tag.decompose()

    for tag in soup.find_all(True, attrs={"aria-hidden": "true"}):
        tag.decompose()
    for tag in soup.find_all(True, style=lambda s: s and "display:none" in s.replace(" ", "").lower()):
        tag.decompose()

    KEEP_TAGS = {
        "h1", "h2", "h3", "h4", "h5", "h6",
        "p", "ul", "ol", "li", "dl", "dt", "dd",
        "strong", "b", "em", "i", "a", "br",
        "div", "span", "section", "article", "main",
        "table", "tr", "td", "th", "thead", "tbody",
        "blockquote", "pre", "code", "hr",
    }

    # Strip all attributes except href on <a> tags
    for tag in soup.find_all(True):
        if tag.name not in KEEP_TAGS:
            tag.unwrap()
        elif tag.name == "a":
            href = tag.get("href", "")
            tag.attrs = {"href": href, "target": "_blank"} if href else {}
        else:
            tag.attrs = {}

    body = soup.body if soup.body else soup
    clean_html = str(body)

    # Collapse excessive whitespace / empty divs
    import re
    clean_html = re.sub(r'(<br\s*/?>[\s]*){3,}', '<br><br>', clean_html)
    clean_html = re.sub(r'(<div>\s*</div>\s*){2,}', '', clean_html)
    clean_html = re.sub(r'\n{3,}', '\n\n', clean_html)

    # Plain text for search/analysis
    text = soup.get_text(separator="\n", strip=True)[:50_000]

    return clean_html[:500_000], text


async def _fetch_with_playwright(url: str) -> str:
    """Fetch a page using Playwright for SPA/JS-rendered sites. Returns raw HTML."""
    from backend.scraper._shared.browser import _get_browser, _new_page, _close_page
    from backend.scraper._shared.url_safety import assert_public_http_url
    # Revalidate here too — this function is also reachable directly, and a
    # single missed caller elsewhere would reopen the SSRF hole.
    assert_public_http_url(url)
    pw, browser = await _get_browser()
    try:
        page = await _new_page(browser)
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)  # Extra time for JS rendering
            return await page.content()
        finally:
            await _close_page(page)
    finally:
        # pw.stop() kills the node driver process; it must run even if closing
        # the browser fails, or the driver outlives every failed fetch.
        try:
            await browser.close()
        except Exception as e:
            logger.warning(f"Playwright browser close failed: {e}")
        await pw.stop()


def _set_job_cache_error(job_id: str, msg: str) -> None:
    """Record why caching gave up, in its own short session."""
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.cache_error = (msg or "")[:500]
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


async def _cache_job_page(job_id: str, url: str):
    """Fetch and cache the job page as clean readable HTML.

    No DB session is open while the page is fetched or parsed: the fetch is an
    HTTP round trip and, for thin pages, a whole Chromium launch. Holding a
    pooled connection across that is what drained the pool when a bulk action
    kicked off dozens of these at once, and running dozens of Chromiums at once
    is what took the container to 2.5 GB -- hence the `page_cache` gate.
    """
    from datetime import datetime, timezone
    from backend.scraper._shared.url_safety import safe_get, assert_public_http_url, UnsafeURLError
    from backend.job_monitor import get_limiter

    if not url:
        return

    db = SessionLocal()
    try:
        if not db.query(Job.id).filter(Job.id == job_id).first():
            return
    finally:
        db.close()

    # SSRF gate: user-submitted job URLs from the extension land here; without
    # it an attacker could cache http://169.254.169.254/ and read it via the UI.
    try:
        assert_public_http_url(url)
    except UnsafeURLError as e:
        logger.warning(f"Rejected unsafe job URL for {job_id}: {e}")
        _set_job_cache_error(job_id, f"unsafe URL: {e}")
        return

    # Track the last error so it can be surfaced to the UI via job.cache_error
    last_error: str | None = None
    clean_html, text = "", ""

    async with get_limiter("page_cache"):
        try:
            # Try httpx first (fast, works for most sites)
            html = None
            try:
                resp = await safe_get(url, timeout=20, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })
                resp.raise_for_status()
                html = resp.text[:1_000_000]
            except UnsafeURLError as e:
                # Caught mid-redirect -- don't fall back to Playwright for unsafe URLs.
                logger.warning(f"Unsafe redirect target for job {job_id}: {e}")
                _set_job_cache_error(job_id, f"unsafe redirect: {e}")
                return
            except Exception as e:
                logger.info(f"httpx failed for job {job_id}, will try Playwright: {e}")
                last_error = f"httpx: {e}"

            # A challenge page has enough text to pass as content, and the cached
            # text is what tailoring falls back to as the JD.
            if is_bot_wall(html):
                last_error = f"httpx: {_BOT_WALL_ERROR}"
                html = None

            clean_html, text = _extract_clean_content(html) if html else ("", "")
            # Up to 1 MB of raw markup plus the soup built from it; drop the
            # reference before the (slow) Playwright branch so it is not pinned
            # for the length of a browser launch.
            html = None

            # If too little content, fall back to Playwright (handles SPAs like Meta, Apple)
            if len(text) < 200:
                logger.info(f"Thin content ({len(text)} chars) for job {job_id}, trying Playwright")
                try:
                    pw_html = await _fetch_with_playwright(url)
                    if is_bot_wall(pw_html):
                        last_error = f"playwright: {_BOT_WALL_ERROR}"
                    elif pw_html:
                        clean_html, text = _extract_clean_content(pw_html)
                        logger.info(f"Playwright got {len(text)} text chars for job {job_id}")
                    pw_html = None
                except Exception as e:
                    logger.warning(f"Playwright fallback failed for job {job_id}: {e}")
                    last_error = f"playwright: {e}"
        except Exception as e:
            logger.warning(f"Failed to cache page for job {job_id}: {e}")
            _set_job_cache_error(job_id, str(e))
            return

    if len(text) > 50:
        db = SessionLocal()
        try:
            job = db.query(Job).filter(Job.id == job_id).first()
            if not job:
                return
            job.cached_page_html = clean_html
            job.cached_page_text = text
            job.page_cached_at = datetime.now(timezone.utc)
            job.cache_error = None
            db.commit()
            logger.info(f"Cached page for job {job_id}: {len(clean_html)} clean HTML, {len(text)} text chars")
        except Exception as e:
            db.rollback()
            logger.warning(f"Failed to store cached page for job {job_id}: {e}")
        finally:
            db.close()
    else:
        msg = last_error or f"no usable content ({len(text)} chars)"
        logger.warning(f"No usable content for job {job_id} ({url}): {msg}")
        _set_job_cache_error(job_id, msg)
