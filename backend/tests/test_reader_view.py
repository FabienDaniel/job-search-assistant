"""GET /api/jobs/{id}/reader: the posting text without the board's page around it."""

import pytest

from backend.tests.r4_support import assert_clean, client, make_job  # noqa: F401

# Trimmed from a real https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/<id> answer.
_GUEST_PAGE = """
<section class="top-card-layout"><a href="https://fr.linkedin.com/company/acme">Acme</a>
  <h2 class="top-card-layout__title">Lead Data Engineer</h2></section>
<div class="description__text description__text--rich">
  <section class="show-more-less-html">
    <div class="show-more-less-html__markup show-more-less-html__markup--clamp-after-5 relative">
      <strong>Contexte et environnement<br><br></strong>Le Lead Data Engineer est le référent.<br><br>
      <ul><li> un Chef de Projet Data ; </li><li> des Data Analysts ; </li></ul>
    </div>
    <button class="show-more-less-html__button">Show more</button>
  </section>
</div>
<ul class="description__job-criteria-list">
  <li class="description__job-criteria-item">
    <h3 class="description__job-criteria-subheader"> Seniority level </h3>
    <span class="description__job-criteria-text description__job-criteria-text--criteria"> Mid-Senior level </span>
  </li>
  <li class="description__job-criteria-item">
    <h3 class="description__job-criteria-subheader"> Employment type </h3>
    <span class="description__job-criteria-text description__job-criteria-text--criteria"> Full-time </span>
  </li>
</ul>
<section class="similar-jobs">Découvrez comment vous vous positionnez</section>
"""


class _Resp:
    def __init__(self, text="", status_code=200):
        self.text = text
        self.status_code = status_code


@pytest.fixture
def guest(monkeypatch):
    """Answer the LinkedIn guest fetch with `guest.resp`, recording the URLs asked for."""
    import backend.scraper._shared.url_safety as us

    class _Guest:
        resp = _Resp(_GUEST_PAGE)
        urls = []

    async def _fake(url, **kw):
        _Guest.urls.append(url)
        if isinstance(_Guest.resp, BaseException):
            raise _Guest.resp
        return _Guest.resp

    monkeypatch.setattr(us, "safe_get", _fake)
    return _Guest


def _linkedin_job(db, **kw):
    return make_job(
        db,
        source="jobspy_linkedin",
        url="https://www.linkedin.com/jobs/view/4489102631",
        posting_key="linkedin:4489102631",
        **kw,
    )


def test_linkedin_job_shows_the_guest_description_and_criteria(client, test_db, guest):
    job = _linkedin_job(test_db, description="flat stored text")
    r = assert_clean(client.get(f"/api/jobs/{job.id}/reader"), 200)
    assert guest.urls == [
        "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/4489102631"
    ]
    assert "<strong>Seniority level</strong> Mid-Senior level" in r.text
    assert "<strong>Employment type</strong> Full-time" in r.text
    assert "<li> un Chef de Projet Data ; </li>" in r.text
    assert "LinkedIn posting" in r.text
    # nothing from around the description block
    for noise in ("Show more", "Découvrez comment", "top-card", "fr.linkedin.com"):
        assert noise not in r.text
    assert "flat stored text" not in r.text
    assert r.headers["content-security-policy"].startswith("sandbox;")


@pytest.mark.parametrize(
    "resp",
    [
        _Resp("", status_code=404),
        _Resp("<html>no description block here</html>"),
        RuntimeError("network down"),
    ],
)
def test_linkedin_failure_falls_back_to_the_stored_description(
    client, test_db, guest, resp
):
    guest.resp = resp
    job = _linkedin_job(test_db, description="Line one\nLine two")
    r = assert_clean(client.get(f"/api/jobs/{job.id}/reader"), 200)
    assert "Line one<br />\nLine two" in r.text or "Line one<br/>\nLine two" in r.text
    assert "Description saved when the job was found" in r.text


def test_markdown_description_is_rendered_and_scripts_dropped(client, test_db, guest):
    job = make_job(
        test_db,
        source="jobspy_indeed",
        description="**Descriptif du poste**\n\n- Python\n- SQL\n\n<script>alert(1)</script>",
    )
    r = assert_clean(client.get(f"/api/jobs/{job.id}/reader"), 200)
    assert "<strong>Descriptif du poste</strong>" in r.text
    assert "<li>Python</li>" in r.text
    assert "<script" not in r.text and "alert(1)" not in r.text
    assert guest.urls == []  # not a LinkedIn posting: no fetch


@pytest.mark.parametrize("description", [None, "", "   \n "])
def test_job_without_any_text_is_404(client, test_db, guest, description):
    job = make_job(test_db, source="jobspy_indeed", description=description)
    assert_clean(client.get(f"/api/jobs/{job.id}/reader"), 404)


def test_unknown_job_is_404(client):
    assert_clean(
        client.get("/api/jobs/00000000-0000-0000-0000-000000000000/reader"), 404
    )


def test_stored_html_is_served_without_a_fetch(client, test_db, guest):
    job = _linkedin_job(test_db, description_html="<p>kept from the scrape</p>")
    r = assert_clean(client.get(f"/api/jobs/{job.id}/reader"), 200)
    assert "<p>kept from the scrape</p>" in r.text
    assert guest.urls == []


def test_a_fetched_posting_is_saved_and_not_fetched_again(client, test_db, guest):
    job = _linkedin_job(test_db)
    first = assert_clean(client.get(f"/api/jobs/{job.id}/reader"), 200)
    test_db.refresh(job)
    assert "<li> un Chef de Projet Data ; </li>" in job.description_html
    second = assert_clean(client.get(f"/api/jobs/{job.id}/reader"), 200)
    assert len(guest.urls) == 1
    assert second.text == first.text


def test_a_rate_limited_fetch_saves_nothing(client, test_db, guest):
    guest.resp = _Resp("", status_code=429)
    job = _linkedin_job(test_db, description="stored text")
    r = assert_clean(client.get(f"/api/jobs/{job.id}/reader"), 200)
    assert "stored text" in r.text
    test_db.refresh(job)
    assert job.description_html is None
