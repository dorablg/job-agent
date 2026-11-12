from datetime import UTC, datetime, timedelta

import pytest

from agent import match
from tests.conftest import make_job

CV = "Python SQL machine learning TensorFlow pandas Docker customer support Zendesk"


@pytest.mark.parametrize("term,text,ok", [
    ("sql", "we use sql daily", True),
    ("sql", "postgresql only", False),          # no partial-word hits
    ("api", "rest apis", True),                  # plural
    ("c++", "modern c++ code", True),            # special characters escaped
    ("go", "we go fast", True),
    ("python", "", False),
])
def test_has_is_whole_word(term, text, ok):
    assert match._has(term, text) is ok


def test_has_matches_reference_regex_exactly():
    """The substring pre-check must never change results compared with the plain regex."""
    import re
    terms = ["sql", "data", "machine learning", "c#", "node.js", "a/b testing", "r", "ai"]
    texts = ["SQL and data".lower(), "node.js, c# and a/b testing", "rag pipelines for ai", "r and rust", "datasets"]
    for t in terms:
        ref = re.compile(r"(?<![a-z0-9])" + re.escape(t) + r"s?(?![a-z0-9])")
        for x in texts:
            assert match._has(t, x) == bool(ref.search(x)), (t, x)


def test_ats_score_counts_matched_and_missing(cfg):
    vocab = match._vocab(cfg)
    score, have, missing = match.ats_score(CV, "We need Python, SQL and Kubernetes", vocab)
    assert "python" in have and "sql" in have and "kubernetes" in missing
    assert 0 < score < 100


def test_written_in_detects_german_not_english():
    de = ("Wir suchen eine erfahrene Person für unser Team und die Aufgaben sind mit der Arbeit bei uns verbunden "
          "und wir bieten eine gute Erfahrung und Kenntnisse in der Arbeit mit Daten und die Kunden sind wichtig")
    en = ("We are looking for a junior analyst to join our team and you will work with the data and the customers "
          "to build reports and dashboards for the business and you are curious and kind and eager to learn")
    assert match.written_in(de) == "German"
    assert match.written_in(en) == ""


@pytest.mark.parametrize("text,emp", [("Part-time, 20 hours per week", "part-time"),
                                      ("This is a full-time role", "full-time"), ("Remote role", "")])
def test_detect_employment(text, emp):
    assert match.detect_employment(text) == emp


def test_filters_drop_old_and_excluded(cfg):
    old = make_job(posted=datetime.now(UTC) - timedelta(days=400))
    assert not match.passes_filters(old, cfg)
    assert match.passes_filters(make_job(posted=datetime.now(UTC)), cfg)


def test_score_jobs_categorises_and_rejects(cfg):
    jobs = [
        make_job(id="a", title="Junior Data Analyst", description="Python, SQL, dashboards. Entry level. " * 3),
        make_job(id="b", title="Senior Staff Engineer", description="10+ years of experience required. Python."),
        make_job(id="c", title="Pastry Chef", description="Bake bread."),
    ]
    out = {j.id: j for j in match.score_jobs(jobs, CV, cfg)}
    assert "c" not in out and "b" not in out
    if "a" in out:
        assert out["a"].category and 0 <= out["a"].score <= 100


def test_curated_only_category_is_never_keyword_matched(cfg):
    jobs = [make_job(id="p", title="MSc Data Science with placement year", kind="fellowship",
                     description="Master's programme with a paid placement year in London.")]
    for j in match.score_jobs(jobs, CV, cfg):
        assert j.category != "🎓 Study + work programs"


def test_expired_programme_by_year_in_title(cfg):
    last_year = datetime.now(UTC).year - 1
    jobs = [make_job(id="y", title=f"AI Summer School {last_year}", kind="event", work_mode="remote",
                     description="Free AI summer school online.")]
    assert match.score_jobs(jobs, CV, cfg) == []
