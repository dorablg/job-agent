import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def cfg() -> dict:
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


@pytest.fixture
def password(monkeypatch) -> str:
    pw = "test-password-not-real"
    monkeypatch.setenv("DASHBOARD_PASSWORD", pw)
    return pw


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Tests never touch the internet or the free AI quota."""
    import requests

    def blocked(*a, **k):
        raise RuntimeError("network disabled in tests")

    monkeypatch.setattr(requests.Session, "request", blocked)
    for var in ("GEMINI_API_KEY", "GROQ_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
                "GMAIL_WEBAPP_URL", "GMAIL_WEBAPP_KEY", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"):
        monkeypatch.delenv(var, raising=False)


def make_job(**kw):
    from agent.sources import Job
    base = dict(id="t-1", title="Junior Data Analyst", company="Acme", url="https://example.com/job",
                description="We use Python and SQL. Entry level.", location="London, United Kingdom",
                kind="job", work_mode="onsite")
    base.update(kw)
    return Job(**base)
