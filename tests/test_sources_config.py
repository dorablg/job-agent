import re
import threading
import time

import pytest

from agent import enrich, sources
from tests.conftest import make_job


def test_pmap_keeps_order_and_runs_in_parallel():
    def slow(x):
        time.sleep(0.2)
        return x * 2
    t0 = time.perf_counter()
    assert sources.pmap(slow, range(8), workers=8) == [0, 2, 4, 6, 8, 10, 12, 14]
    assert time.perf_counter() - t0 < 1.0


def test_fetch_all_isolates_failures_and_keeps_config_order(monkeypatch):
    seen_threads = set()
    def ok(_terms):
        seen_threads.add(threading.get_ident())
        time.sleep(0.05)
        return [make_job(id="ok", title="A &amp;amp; B")]
    def boom(_terms):
        raise RuntimeError("down")
    def ok2(_terms):
        seen_threads.add(threading.get_ident())
        return [make_job(id="ok2")]
    monkeypatch.setattr(sources, "SOURCES", {"ok": ok, "boom": boom, "ok2": ok2})
    logs = []
    jobs = sources.fetch_all({"sources": ["ok", "boom", "ok2", "missing"]}, log=logs.append)
    assert [j.id for j in jobs] == ["ok", "ok2"]
    assert jobs[0].title == "A & B"                                   # double-escaped titles fixed
    assert any("boom: FAILED" in line for line in logs)


def test_workable_parsing_and_location_rules(monkeypatch):
    sources.set_focus(["London", "Italy"])
    payload = {"jobs": [
        {"id": 1, "title": "Data Analyst", "location": {"city": "London", "countryName": "United Kingdom"}, "workplace": "on_site"},
        {"id": 2, "title": "Data Analyst", "location": {"city": "Sofia", "countryName": "Bulgaria"}, "workplace": "on_site"},
        {"id": 1, "title": "Duplicate", "location": {"city": "London", "countryName": "United Kingdom"}},
    ]}
    monkeypatch.setattr(sources, "_get", lambda url, **kw: payload)
    out = sources.workable(None, [{"location": "London", "queries": ["data", "ml"]}])
    assert [j.id for j in out] == ["workable-1"]


def test_clean_strips_html():
    assert sources.clean("<p>Hello&amp;<b>world</b></p><script>x</script>") .startswith("Hello&")


# ---------------------------------------------------------------- config sanity (catches typos before a run)
def test_config_categories_are_well_formed(cfg):
    names = [c["name"] for c in cfg["categories"]]
    assert len(names) == len(set(names))
    for c in cfg["categories"]:
        assert c.get("tiers") or c.get("must_any"), c["name"]
        for k in c.get("kinds", []):
            assert k in ("job", "internship", "fellowship", "event"), (c["name"], k)


def test_curated_items_are_valid_and_point_to_real_categories(cfg):
    names = {c["name"] for c in cfg["categories"]}
    for it in cfg.get("curated", []):
        assert it["category"] in names, it["title"]
        assert it["url"].startswith("https://"), it["title"]
        assert it.get("kind", "event") in ("job", "internship", "fellowship", "event"), it["title"]  # loader default
        assert 0 <= int(it.get("chance", 50)) <= 100
        dl = str(it.get("deadline", ""))
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", dl):
            assert enrich.deadline_strict(f"deadline: {dl}") == dl


def test_curated_loader(cfg):
    jobs = sources.curated(None, cfg["curated"])
    assert len(jobs) == len(cfg["curated"])
    assert all(j.check and j.check.get("keep") for j in jobs)
    assert any(j.category == "🎓 Study + work programs" for j in jobs)


@pytest.mark.parametrize("name", ["sources", "focus_places", "categories", "curated"])
def test_config_has_section(cfg, name):
    assert cfg.get(name)
