"""JavaScript checks: syntax of every script, and Python <-> WebCrypto encryption compatibility."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from agent import dashboard, secure
from tests.conftest import make_job

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(not NODE, reason="node is not installed")


@pytest.mark.parametrize("path", sorted(str(p.relative_to(ROOT)) for p in (ROOT / "extension").glob("*.js")))
def test_extension_js_syntax(path):
    subprocess.run([NODE, "--check", str(ROOT / path)], check=True)


def test_dashboard_inline_script_syntax(tmp_path):
    html = dashboard.TEMPLATE.read_text(encoding="utf-8").replace("__PAYLOAD__", "{}")
    script = re.search(r"<script>(.*?)</script>", html, re.DOTALL).group(1)
    f = tmp_path / "dashboard.js"
    f.write_text(script, encoding="utf-8")
    subprocess.run([NODE, "--check", str(f)], check=True)


def test_apps_script_syntax(tmp_path):
    f = tmp_path / "bridge.js"
    f.write_text((ROOT / "agent" / "gmail_bridge_template.gs").read_text(encoding="utf-8"), encoding="utf-8")
    subprocess.run([NODE, "--check", str(f)], check=True)


def test_python_blob_decrypts_in_extension(tmp_path):
    rec = dashboard.record(make_job(id="x"), None)
    blob = secure.encrypt(json.dumps({"listings": [rec]}).encode(), "pw-123", salt=b"0123456789abcdef")
    f = tmp_path / "blob.json"
    f.write_text(json.dumps(blob), encoding="utf-8")
    r = subprocess.run([NODE, str(ROOT / "tests" / "js" / "core_test.js"), str(f), "pw-123"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr + r.stdout
    assert "core.js OK" in r.stdout
