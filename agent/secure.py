"""Password encryption (AES-256-GCM + PBKDF2) shared by Python and the dashboard (WebCrypto).

Everything personal (your CV, contact details, cover letters) is stored encrypted, so the
GitHub repo and website can be public and free while only you can read them.

  python -m agent.secure lock     # cv/ folder  -> cv.enc   (run after changing your CV)
  python -m agent.secure unlock   # cv.enc      -> cv/      (GitHub Actions does this)
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ROOT = Path(__file__).resolve().parent.parent
ITER = 250_000


def _key(password: str, salt: bytes, iterations: int = ITER) -> bytes:
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations).derive(
        password.encode("utf-8"))


def encrypt(data: bytes, password: str) -> dict:
    salt, iv = os.urandom(16), os.urandom(12)
    ct = AESGCM(_key(password, salt)).encrypt(iv, data, None)
    b = lambda x: base64.b64encode(x).decode()
    return {"v": 1, "iter": ITER, "salt": b(salt), "iv": b(iv), "ct": b(ct)}


def decrypt(blob: dict, password: str) -> bytes:
    d = lambda k: base64.b64decode(blob[k])
    return AESGCM(_key(password, d("salt"), blob.get("iter", ITER))).decrypt(d("iv"), d("ct"), None)


def password() -> str:
    pw = os.getenv("DASHBOARD_PASSWORD", "")
    if not pw:
        raise SystemExit("DASHBOARD_PASSWORD is not set (in .env locally, or as a GitHub secret).")
    return pw


def lock_cv() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in (ROOT / "cv").iterdir():
            if f.is_file() and f.name.lower() != "readme.md":
                z.write(f, f.name)
    (ROOT / "cv.enc").write_text(json.dumps(encrypt(buf.getvalue(), password())), encoding="utf-8")
    print("cv/ encrypted -> cv.enc")


def unlock_cv() -> None:
    blob = json.loads((ROOT / "cv.enc").read_text(encoding="utf-8"))
    with zipfile.ZipFile(io.BytesIO(decrypt(blob, password()))) as z:
        z.extractall(ROOT / "cv")
    print("cv.enc decrypted -> cv/")


if __name__ == "__main__":
    from .main import load_env
    load_env()
    {"lock": lock_cv, "unlock": unlock_cv}[sys.argv[1]]()
