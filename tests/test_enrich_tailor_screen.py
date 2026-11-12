import pytest

from agent import enrich, screen, tailor


@pytest.mark.parametrize("loc,text,want", [
    ("Remote", "We hire worldwide", "yes"),
    ("Online", "", "yes"),
    ("Remote", "Must be based in the US", "no"),
])
def test_tunisia_eligibility(loc, text, want):
    assert enrich.tunisia(loc, text) == want


@pytest.mark.parametrize("text,want", [
    ("Application deadline: 15 March 2027", "2027-03-15"),
    ("apply by 2027-01-28", "2027-01-28"),
    ("Deadline: rolling", ""),
])
def test_deadline_strict(text, want):
    assert enrich.deadline_strict(text) == want


def test_experience_and_visa():
    assert enrich.experience_years("Requires 5+ years of experience in Python") == 5
    assert enrich.experience_years("entry-level role") == 0
    assert enrich.visa("Visa sponsorship is available") == "sponsor"


def test_student_rules(cfg):
    job_cat = "🏢 Job (UK, Italy, Europe, Gulf)"
    assert not tailor.is_student(job_cat, cfg, "job", "Data Analyst")
    assert tailor.is_student(job_cat, cfg, "internship", "Data intern")
    assert tailor.is_student(job_cat, cfg, "job", "Werkstudent Data")
    assert tailor.is_student("🎓 Study + work programs", cfg, "fellowship", "MSc")
    assert tailor.student_rule(job_cat, cfg, "job", "Analyst") == tailor.STUDENT_NO


def test_scrub_studies_removes_every_mention_but_keeps_the_rest():
    ai = {"cover_letter": "Dear team,\nI am currently studying at Polytechnique de Sousse. I love data! Thanks.",
          "ats_cv": {"summary": "Data analyst. Engineering degree in progress at Polytech.",
                     "education": [{"degree": "BSc CS", "school": "ISITCOM"},
                                   {"degree": "Engineering degree", "school": "Polytechnique de Sousse"}]}}
    out = tailor.scrub_studies(ai)
    assert not tailor.mentions_studies(out)
    assert out["cover_letter"].startswith("Dear team,\nI love data!")
    assert out["ats_cv"]["education"] == [{"degree": "BSc CS", "school": "ISITCOM"}]


@pytest.mark.parametrize("check,ok", [
    ({"keep": True, "chance": 60, "visa": "none"}, True),
    ({"keep": True, "chance": 30, "visa": "none"}, False),
    ({"keep": False, "chance": 90, "visa": "none"}, False),
    ({"keep": True, "chance": 90, "visa": "blocked"}, False),
    (None, False),
])
def test_screen_passes(check, ok):
    assert screen.passes(check) is ok


def test_screen_parses_and_clamps_model_output(monkeypatch):
    monkeypatch.setattr(screen.llm, "available", lambda: True)
    monkeypatch.setattr(screen.llm, "ask_json", lambda *a, **k: {"results": [
        {"id": "a", "keep": True, "chance": 150, "family": "ml_ai", "visa": "none", "why": "fits"},
        {"id": "zzz", "keep": True, "chance": 90},                    # unknown id is ignored
        {"id": "b", "keep": "yes", "chance": "n/a"},                   # junk numbers become 0
    ]})
    out = screen.screen([{"id": "a", "title": "x"}, {"id": "b", "title": "y"}])
    assert out["a"]["chance"] == 100 and "zzz" not in out and out["b"]["chance"] == 0
