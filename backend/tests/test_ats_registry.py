"""ats.registry is the one list of ATS handlers that the run, the Test scrape and the labels read."""
import importlib
import pkgutil

import backend.scraper.ats as ats_pkg
from backend.scraper.ats import registry


def test_every_handler_module_is_registered():
    """A handler module left out of HANDLERS is silently read by the generic scraper."""
    registered = {h.name for h in registry.HANDLERS}
    for info in pkgutil.iter_modules(ats_pkg.__path__):
        module = importlib.import_module(f"backend.scraper.ats.{info.name}")
        if hasattr(module, f"is_{info.name}"):
            assert info.name in registered, f"ats/{info.name}.py is not in registry.HANDLERS"


def test_labels():
    assert registry.scrape_type("https://nvidia.wd5.myworkdayjobs.com/CareerSite") == "Workday API"
    assert registry.scrape_type("https://jobs.uber.com/en/jobs/?team=Product") == "Uber API"
    assert registry.scrape_type("https://www.metacareers.com/jobs") == "Meta Careers (Playwright)"
    assert registry.scrape_type("https://careers.example.com/jobs") == registry.GENERIC_LABEL


def test_a_phenom_spec_wins_over_its_host():
    """The label follows the dispatch order, so it names the handler that really reads the URL."""
    spec = 'POST|https://acme.wd1.myworkdayjobs.com/api/jobs|{"q": "pm"}'
    assert registry.detect(spec).name == "phenom"
    assert registry.scrape_type(spec) == "Phenom API"


def test_needs_browser():
    assert not registry.needs_browser(["https://jobs.lever.co/acme", "  ", None])
    assert registry.needs_browser(["https://jobs.lever.co/acme", "https://www.metacareers.com/jobs"])
    assert registry.needs_browser(["https://careers.example.com/jobs"])
    assert not registry.needs_browser([])
