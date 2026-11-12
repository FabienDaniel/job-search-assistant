"""The body of a posting's reader view: the posting text without the board's own page around it.

A LinkedIn posting is read from LinkedIn's public guest endpoint, which serves the
description with its headings and lists. Any other job shows the description stored
when it was found, which jobspy writes as Markdown.
"""

import html
import logging
import re

from bs4 import BeautifulSoup

from backend.scraper._shared.bot_wall import is_bot_wall
from backend.scraper._shared.page_cache import _extract_clean_content
from backend.scraper.ats._descriptions import _LINKEDIN_DESCRIPTION_SELECTOR

logger = logging.getLogger("jobnavigator.scraper.reader")

_LINKEDIN_GUEST = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{}"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
}


def _criteria_html(soup) -> str:
    """Seniority, employment type, function and industries as one line of label · value pairs."""
    pairs = []
    for item in soup.select(".description__job-criteria-item"):
        label = item.select_one(".description__job-criteria-subheader")
        value = item.select_one(".description__job-criteria-text")
        if label and value:
            pairs.append(
                f"<strong>{html.escape(label.get_text(strip=True))}</strong>"
                f" {html.escape(value.get_text(strip=True))}"
            )
    return f"<p>{' · '.join(pairs)}</p><hr>" if pairs else ""


def linkedin_html(page: str) -> str | None:
    """The criteria line and cleaned description from a guest posting page, or None without one."""
    soup = BeautifulSoup(page, "html.parser")
    block = soup.select_one(_LINKEDIN_DESCRIPTION_SELECTOR)
    if block is None:
        return None
    clean, text = _extract_clean_content(str(block))
    if not text.strip():
        return None
    return _criteria_html(soup) + clean


async def linkedin_posting(posting_id: str) -> str | None:
    """Fetch a LinkedIn posting from the guest endpoint. None when LinkedIn does not serve it."""
    from backend.scraper._shared.url_safety import safe_get

    if not re.fullmatch(r"\d+", posting_id or ""):
        return None
    try:
        resp = await safe_get(
            _LINKEDIN_GUEST.format(posting_id), timeout=15, headers=_HEADERS
        )
    except Exception as e:
        logger.info(f"LinkedIn guest fetch failed for {posting_id}: {e}")
        return None
    if resp.status_code != 200 or is_bot_wall(resp.text):
        logger.info(f"LinkedIn guest page {posting_id} answered {resp.status_code}")
        return None
    return linkedin_html(resp.text[:2_000_000])


# Tags that start a new line on their own, so a <br> beside one adds a blank line.
_BLOCKS = {
    "p", "li", "ul", "ol", "dl", "dt", "dd", "div", "section", "article", "main",
    "table", "tr", "td", "th", "thead", "tbody", "blockquote", "pre", "hr",
    "h1", "h2", "h3", "h4", "h5", "h6",
}  # fmt: skip


def _at_block_edge(br, forward: bool) -> bool:
    """True when only whitespace and other <br>s lie between `br` and a block boundary."""
    node = br
    while True:
        sib = node.next_sibling if forward else node.previous_sibling
        while sib is not None:
            if isinstance(sib, str):
                if sib.strip():
                    return False
            elif sib.name in _BLOCKS:
                return True
            elif sib.name != "br":
                return False
            sib = sib.next_sibling if forward else sib.previous_sibling
        node = node.parent
        # Leaving an inline wrapper continues the walk in its parent.
        if node is None or node.name in _BLOCKS or node.name == "[document]":
            return True


def tighten_breaks(body: str) -> str:
    """Drop the <br>s that sit beside a block boundary, and the blocks left empty.

    LinkedIn ends every paragraph with <br><br> inside its <p>, which doubles the
    gap the paragraph margin already gives.
    """
    soup = BeautifulSoup(body, "html.parser")
    # html.parser nests a <br/> inside a preceding bare <br>. Flatten them first.
    for br in soup.find_all("br"):
        for child in reversed(list(br.contents)):
            br.insert_after(child.extract())
    for br in [
        b
        for b in soup.find_all("br")
        if _at_block_edge(b, True) or _at_block_edge(b, False)
    ]:
        br.decompose()
    for tag in soup.find_all(["p", "div"]):
        if tag.decomposed:
            continue
        if not tag.get_text(strip=True) and not tag.find(["hr", "table", "ul", "ol"]):
            tag.decompose()
    return str(soup)


def description_html(text: str) -> str | None:
    """The stored description rendered from Markdown, reduced to the reader's allowed tags."""
    import markdown

    if not (text or "").strip():
        return None
    # nl2br: LinkedIn descriptions are stored as flat text with one line per paragraph,
    # which plain Markdown would merge into a single block.
    clean, plain = _extract_clean_content(markdown.markdown(text, extensions=["nl2br"]))
    return clean if plain.strip() else None
