import base64
import hashlib
import json
import re

from agent import dashboard, main, secure, sources, telegram
from tests.conftest import make_job


def test_unique_keeps_the_copy_with_a_kit_and_order():
    rows = [{"id": "1", "title": "Data Analyst (Remote)", "company": "Acme"},
            {"id": "2", "title": "data analyst  remote", "company": "acme", "ai": {"x": 1}},
            {"id": "3", "title": "Other", "company": "B"}]
    assert [r["id"] for r in dashboard._unique(rows)] == ["2", "3"]


def test_upsert_keeps_first_seen_date_and_kit():
    listings = {"a": {"id": "a", "found": "2026-01-01", "ai": {"k": 1}}}
    dashboard.upsert(listings, {"id": "a", "found": "2026-11-01"})
    assert listings["a"]["found"] == "2026-01-01" and listings["a"]["ai"] == {"k": 1}


def test_build_encrypts_and_pins_csp(tmp_path, monkeypatch, password, cfg):
    monkeypatch.setattr(dashboard, "SITE", tmp_path)
    monkeypatch.setattr(secure, "SALT_FILE", tmp_path / "salt.txt")
    listings = {"x": dashboard.record(make_job(id="x"), None)}
    out = dashboard.build(listings, "my cv", cfg, [])
    html = out.read_text(encoding="utf-8")
    assert "__PAYLOAD__" not in html and "__CSP__" not in html
    assert "my cv" not in html and "Junior Data Analyst" not in html           # nothing personal in clear
    blob = json.loads(re.search(r"const BLOB = (\{[^\n]*?\});", html).group(1))
    data = json.loads(secure.decrypt(blob, password))
    assert data["listings"][0]["id"] == "x" and data["db"] is None
    csp = re.search(r'Content-Security-Policy" content="([^"]+)"', html).group(1)
    script = re.search(r"<script>(.*?)</script>", html, re.DOTALL).group(1)
    digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    assert f"'sha256-{digest}'" in csp and "unsafe-inline" not in csp.split("style-src")[0]
    assert "default-src 'none'" in csp and "object-src 'none'" in csp
    # stable salt: a second build reuses it, so "keep me signed in" keeps working
    blob2 = json.loads(re.search(r"const BLOB = (\{[^\n]*?\});", dashboard.build(listings, "cv", cfg, []).read_text(encoding="utf-8")).group(1))
    assert blob2["salt"] == blob["salt"] and blob2["iv"] != blob["iv"]


def test_template_has_no_inline_handlers_or_unsafe_links():
    html = dashboard.TEMPLATE.read_text(encoding="utf-8")
    assert not re.search(r"\son(click|load|error|submit|change|input)=\"", html)
    assert "<script>" in html and html.count("<script") == 1
    assert 'href="${esc(r.url)}"' not in html and 'href="${esc(m.link)}"' not in html
    assert 'localStorage.setItem("pw"' not in html and 'store("pw", pw)' not in html


def test_format_card_escapes_html():
    j = make_job(title="<script>x</script>", company="A&B")
    j.check = {"chance": 70, "why": "<b>bad</b>", "visa": "none"}
    card = main.format_card(j, None)
    assert "<script>" not in card and "&lt;script&gt;" in card and "A&amp;B" in card and "&lt;b&gt;bad" in card


def test_new_jobs_dedupes_by_id_and_title_company():
    a, b, c = make_job(id="1"), make_job(id="2"), make_job(id="3", title="Other")
    assert [j.id for j in main.new_jobs([a, b, c], {})] == ["1", "3"]
    assert [j.id for j in main.new_jobs([a, c], {"3": "x"})] == ["1"]


def test_prune_removes_expired_closed_and_foreign(cfg, monkeypatch):
    monkeypatch.setattr(sources, "BOARDS_OK", {"lever-acme"})
    monkeypatch.setattr(sources, "LIVE_IDS", {"lever-acme-live"})
    de = ("Wir suchen eine erfahrene Person für unser Team und die Aufgaben sind mit der Arbeit bei uns verbunden "
          "und wir bieten eine gute Erfahrung und Kenntnisse in der Arbeit mit Daten und die Kunden sind wichtig")
    listings = {
        "lever-acme-live": {"title": "Analyst", "description": "English text"},
        "lever-acme-gone": {"title": "Analyst", "description": "English text"},
        "x-expired": {"title": "Grant", "description": "Application deadline: 1 January 2020"},
        "x-german": {"title": "Analyst", "description": de},
        "x-ok": {"title": "Analyst", "description": "Apply by 2099-01-01"},
    }
    removed = main.prune(listings, cfg, "2026-11-12")
    assert sorted(listings) == ["lever-acme-live", "x-ok"] and removed == 3


def test_send_alerts_marks_only_delivered(monkeypatch, cfg):
    sent = []
    monkeypatch.setattr(main.tailor, "generate", lambda *a: None)
    def flaky(text, url=None, button=""):
        if url and "fail" in url:
            raise RuntimeError("telegram down")
        sent.append(url)
    monkeypatch.setattr(telegram, "send_text", flaky)
    ok, bad = make_job(id="ok"), make_job(id="bad", url="https://fail.example")
    for j in (ok, bad):
        j.check, j.category = {"chance": 80}, "x"
    _, delivered = main.send_alerts([ok, bad], "cv", cfg, send=True)
    assert delivered == {"ok"}


def test_telegram_only_attaches_web_links(monkeypatch):
    calls = []
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    monkeypatch.setattr(telegram, "_call", lambda m, d=None, files=None: calls.append(d))
    telegram.send_text("hi", url="javascript:alert(1)")
    telegram.send_text("hi", url="https://ok.example")
    assert "javascript:" not in json.dumps(calls[0]) and "https://ok.example" in calls[1]["reply_markup"]
