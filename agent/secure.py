"""Password encryption (AES-256-GCM + PBKDF2-SHA256) shared by Python, the dashboard and the extension (WebCrypto).

Everything personal (your CV, contact details, cover letters) is stored encrypted, so the
GitHub repo and website can be public and free while only you can read them.

  python -m agent.secure lock     # cv/ folder  -> cv.enc   (run after changing your CV)
  python -m agent.secure unlock   # cv.enc      -> cv/      (GitHub Actions does this)

Blob format: {"v": 1, "iter": <PBKDF2 rounds>, "salt": b64, "iv": b64, "ct": b64 (ciphertext + GCM tag)}.
Old blobs keep working: decryption always uses the blob's own salt and iteration count.
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys
import zipfile
from functools import lru_cache
from pathlib import Path, PurePosixPath

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ROOT = Path(__file__).resolve().parent.parent
ITER = 600_000          # OWASP 2023 recommendation for PBKDF2-HMAC-SHA256
SALT_FILE = ROOT / "state" / "site_salt.txt"


@lru_cache(maxsize=8)
def _key(password: str, salt: bytes, iterations: int = ITER) -> bytes:
    """Derived keys are cached per (password, salt, rounds): a run encrypts several blobs with the site salt."""
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations).derive(
        password.encode("utf-8"))


def _b64(x: bytes) -> str:
    return base64.b64encode(x).decode()


def encrypt(data: bytes, password: str, salt: bytes | None = None) -> dict:
    """A fresh random 96-bit IV every call (never reused with the same key); salt is random unless given."""
    salt = salt or os.urandom(16)
    iv = os.urandom(12)
    ct = AESGCM(_key(password, salt)).encrypt(iv, data, None)
    return {"v": 1, "iter": ITER, "salt": _b64(salt), "iv": _b64(iv), "ct": _b64(ct)}


def decrypt(blob: dict, password: str) -> bytes:
    """Raises cryptography.exceptions.InvalidTag on a wrong password or tampered data."""
    def d(k: str) -> bytes:
        return base64.b64decode(blob[k])
    return AESGCM(_key(password, d("salt"), int(blob.get("iter", 250_000)))).decrypt(d("iv"), d("ct"), None)


def site_salt() -> bytes:
    """Stable, public, per-installation salt for the website blob. A stable salt lets the browser keep a
    non-extractable derived key ("keep me signed in") instead of storing the password. Salts don't need to be
    secret; they only need to be unique to this site, which a random value is."""
    env = os.getenv("DASHBOARD_SALT", "").strip()
    if env:
        return base64.b64decode(env)
    if SALT_FILE.exists():
        return base64.b64decode(SALT_FILE.read_text(encoding="utf-8").strip())
    salt = os.urandom(16)
    SALT_FILE.parent.mkdir(exist_ok=True)
    SALT_FILE.write_text(_b64(salt), encoding="utf-8")
    return salt


def password() -> str:
    pw = os.getenv("DASHBOARD_PASSWORD", "")
    if not pw:
        raise SystemExit("DASHBOARD_PASSWORD is not set (in .env locally, or as a GitHub secret).")
    return pw


def lock_cv() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted((ROOT / "cv").iterdir()):
            if f.is_file() and f.name.lower() != "readme.md":
                z.write(f, f.name)
    (ROOT / "cv.enc").write_text(json.dumps(encrypt(buf.getvalue(), password())), encoding="utf-8")
    print("cv/ encrypted -> cv.enc")


def safe_extract(z: zipfile.ZipFile, dest: Path) -> list[Path]:
    """Extracts only plain files directly inside dest (no absolute paths, no '..', no sub-folders)."""
    out = []
    dest.mkdir(parents=True, exist_ok=True)
    for info in z.infolist():
        name = PurePosixPath(info.filename.replace("\\", "/"))
        if info.is_dir() or name.is_absolute() or len(name.parts) != 1 or name.name in ("", ".", ".."):
            raise ValueError(f"refusing unsafe archive entry: {info.filename!r}")
        target = dest / name.name
        target.write_bytes(z.read(info))
        out.append(target)
    return out


def unlock_cv() -> None:
    blob = json.loads((ROOT / "cv.enc").read_text(encoding="utf-8"))
    with zipfile.ZipFile(io.BytesIO(decrypt(blob, password()))) as z:
        safe_extract(z, ROOT / "cv")
    print("cv.enc decrypted -> cv/")


if __name__ == "__main__":
    from .main import load_env
    load_env()
    {"lock": lock_cv, "unlock": unlock_cv}[sys.argv[1]]()
