"""Which ATS handler reads a career-page URL.

One ordered list for the scheduled scrape, the company Test scrape, target keys,
telemetry and the dashboard's ATS chip, so they always agree on a URL.

Order matters. Phenom's `POST|` spec, TalentBrew's AJAX path and Oracle's `/sites/`
path can sit on any host, so they are checked before the hostname matches.
A URL no handler claims goes to `ats.generic`.

`frontend/src/screens/Companies.jsx` (`detectAts`) mirrors this list for the live chip.
"""

from dataclasses import dataclass
from types import ModuleType
from typing import Optional

from backend.scraper.ats import (
    amazon,
    ashby,
    google,
    greenhouse,
    lever,
    meta,
    oracle_hcm,
    phenom,
    rippling,
    smartrecruiters,
    talentbrew,
    uber,
    workday,
)

GENERIC_LABEL = "Generic (Playwright)"


@dataclass(frozen=True)
class Handler:
    module: ModuleType
    label: str  # shown on the ATS chip and in activity lines
    browser: bool = (
        False  # scrape() drives Playwright and takes browser= and max_pages=
    )

    @property
    def name(self) -> str:
        return self.module.__name__.rsplit(".", 1)[1]

    # Looked up on the module at call time, so tests can patch `ats.<name>.scrape`.
    def matches(self, url: str) -> bool:
        return getattr(self.module, f"is_{self.name}")(url)

    async def scrape(
        self,
        url: str,
        debug: bool = False,
        browser=None,
        max_pages: Optional[int] = None,
    ):
        if self.browser:
            return await self.module.scrape(
                url, browser=browser, max_pages=max_pages, debug=debug
            )
        return await self.module.scrape(url, debug=debug)


HANDLERS: tuple[Handler, ...] = (
    Handler(phenom, "Phenom API"),
    Handler(talentbrew, "TalentBrew AJAX"),
    Handler(oracle_hcm, "Oracle HCM API"),
    Handler(lever, "Lever API"),
    Handler(workday, "Workday API"),
    Handler(ashby, "Ashby API"),
    Handler(greenhouse, "Greenhouse API"),
    Handler(rippling, "Rippling API"),
    Handler(smartrecruiters, "SmartRecruiters API"),
    Handler(amazon, "Amazon API"),
    Handler(uber, "Uber API"),
    Handler(meta, "Meta Careers (Playwright)", browser=True),
    Handler(google, "Google Careers (Playwright)", browser=True),
)


def detect(url: str) -> Optional[Handler]:
    """The handler that reads this URL, or None for the generic reader."""
    for handler in HANDLERS:
        if handler.matches(url):
            return handler
    return None


def scrape_type(url: str) -> str:
    """The ATS label of a URL ("Workday API", "Generic (Playwright)"). No network calls."""
    handler = detect(url)
    return handler.label if handler else GENERIC_LABEL


def needs_browser(urls) -> bool:
    """True when any URL is read through Playwright: a browser handler or the generic reader."""
    for url in urls:
        url = (url or "").strip()
        if not url:
            continue
        handler = detect(url)
        if handler is None or handler.browser:
            return True
    return False
