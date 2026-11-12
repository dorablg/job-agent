import base64
import io
import zipfile

import pytest
from cryptography.exceptions import InvalidTag

from agent import secure


def test_round_trip_and_fresh_iv():
    a = secure.encrypt(b"secret data", "pw")
    b = secure.encrypt(b"secret data", "pw")
    assert secure.decrypt(a, "pw") == b"secret data"
    assert a["iv"] != b["iv"] and a["ct"] != b["ct"]          # IV never reused
    assert a["iter"] == secure.ITER >= 600_000


def test_wrong_password_and_tampering_are_rejected():
    blob = secure.encrypt(b"x" * 100, "right")
    with pytest.raises(InvalidTag):
        secure.decrypt(blob, "wrong")
    ct = bytearray(base64.b64decode(blob["ct"]))
    ct[0] ^= 1
    with pytest.raises(InvalidTag):
        secure.decrypt({**blob, "ct": base64.b64encode(bytes(ct)).decode()}, "right")


def test_old_blobs_with_fewer_rounds_still_open():
    salt = b"s" * 16
    key = secure._key("pw", salt, 250_000)
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    ct = AESGCM(key).encrypt(b"i" * 12, b"legacy", None)
    blob = {"v": 1, "iter": 250_000, "salt": base64.b64encode(salt).decode(),
            "iv": base64.b64encode(b"i" * 12).decode(), "ct": base64.b64encode(ct).decode()}
    assert secure.decrypt(blob, "pw") == b"legacy"


def test_stable_site_salt(tmp_path, monkeypatch):
    monkeypatch.setattr(secure, "SALT_FILE", tmp_path / "salt.txt")
    monkeypatch.delenv("DASHBOARD_SALT", raising=False)
    s1, s2 = secure.site_salt(), secure.site_salt()
    assert s1 == s2 and len(s1) == 16
    blob = secure.encrypt(b"d", "pw", salt=s1)
    assert base64.b64decode(blob["salt"]) == s1


@pytest.mark.parametrize("name", ["../evil.txt", "/abs.txt", "sub/dir.txt", "..\\win.txt"])
def test_safe_extract_refuses_path_tricks(tmp_path, name):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(name, "x")
    with zipfile.ZipFile(buf) as z, pytest.raises(ValueError):
        secure.safe_extract(z, tmp_path / "out")


def test_safe_extract_plain_files(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("cv.pdf", "pdf")
        z.writestr("profile.txt", "hi")
    with zipfile.ZipFile(buf) as z:
        out = secure.safe_extract(z, tmp_path)
    assert sorted(p.name for p in out) == ["cv.pdf", "profile.txt"]
