"""Career refocus: no front-office customer service, paid internships only, contract & freelance work first."""
import pytest

from agent import main, match, sources
from tests.conftest import make_job

CV = "Python SQL machine learning TensorFlow pandas Docker data annotation"


def test_yaml_yes_is_understood_as_the_word_yes():
    assert match._yes_no([True, "check", False, "Yes"]) == ["yes", "check", "no", "yes"]


@pytest.mark.parametrize("title", ["Customer Service Representative-Remote", "Online Chat Support-Part time",
                                   "Junior Customer Support Associate", "Call Centre Agent (French)", "Receptionist"])
def test_front_office_titles_are_excluded(cfg, title):
    assert match.title_excluded(title, cfg)


@pytest.mark.parametrize("title", ["Technical Support Engineer", "Application Support Analyst", "Junior Data Analyst",
                                   "Customer Support Engineer (API)", "AI Data Quality Analyst"])
def test_technical_roles_are_kept(cfg, title):
    assert not match.title_excluded(title, cfg)


@pytest.mark.parametrize("text,emp", [
    ("Employment type: freelance hourly contract. Pay: $50/hr", "contract"),
    ("6-month contract role, fully remote", "contract"),
    ("Part-time contract, 20 hours per week", "part-time"),
    ("Permanent full-time position", "full-time"),
    ("We offer a great employment contract and full-time hours", "full-time"),
])
def test_contract_detection(text, emp):
    assert match.detect_employment(text) == emp


def test_unpaid_internships_are_dropped_but_paid_ones_kept(cfg):
    unpaid = make_job(id="u", kind="internship", title="Data Science Intern", description="This is an unpaid internship.")
    paid = make_job(id="p", kind="internship", title="Data Science Intern", description="Paid internship, €1,200 per month.")
    assert not match.passes_filters(unpaid, cfg)
    assert match.passes_filters(paid, cfg)


def test_remote_contract_lands_in_the_contract_category(cfg):
    j = make_job(id="c", title="Python Developer", location="Remote (worldwide)", work_mode="remote",
                 description="Employment type: freelance hourly contract (paid weekly). Pay: $60-90/hr. Remote. "
                             "Review AI-written Python code from anywhere.")
    out = match.score_jobs([j], CV, cfg)
    assert out and out[0].category.startswith("💵 Contract")


def test_alignerr_keeps_open_roles_and_drops_local_senior_or_language_ones(monkeypatch):
    rows = [
        {"id": "1", "title": "AI Data Quality Analyst", "description": "Review AI outputs from anywhere.", "pay": "$40-120/hr", "applyUrl": "/jobs/1"},
        {"id": "2", "title": "French Workspace Evaluator", "description": "Native French speaker in Paris? Get paid", "pay": "$15/hr"},
        {"id": "3", "title": "Principal Python Engineer", "description": "Senior engineers", "pay": "$90/hr"},
        {"id": "4", "title": "Japanese Voice AI Evaluator", "description": "Native speakers", "pay": "$20/hr"},
        {"id": "5", "title": "ML Engineer", "description": "ML engineers in Warsaw — get paid", "pay": "$90/hr"},
        {"id": "6", "title": "AI Data Quality Analyst", "description": "Same role, another post.", "pay": "$40/hr"},
    ]
    monkeypatch.setattr(sources, "_get", lambda url, **kw: {"jobs": rows})
    out = sources.alignerr(None, {"searches": ["a", "b"]})
    assert [j.id for j in out] == ["alignerr-1"]
    assert out[0].url == "https://www.alignerr.com/jobs/1" and out[0].salary == "$40-120/hr"
    assert match.detect_employment(out[0].description) == "contract"


def test_prune_removes_front_office_but_not_curated_programmes(cfg):
    listings = {
        "x-cs": {"title": "Customer Service Representative-Remote", "description": "Answer calls."},
        "x-tech": {"title": "Technical Support Engineer", "description": "Linux, APIs."},
        "x-uc3m": {"title": "Master in Big Data Analytics — Universidad Carlos III de Madrid", "source": "Curated (web research)",
                   "description": "Programme."},
        "x-unpaid": {"title": "AI Intern", "kind": "internship", "description": "This is an unpaid internship."},
    }
    main.prune(listings, cfg, "2026-11-18")
    assert sorted(listings) == ["x-tech", "x-uc3m"]
