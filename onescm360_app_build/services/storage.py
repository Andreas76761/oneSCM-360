"""File-based storage: atomic JSON writes, IDs and path helpers.

All persistent state lives below a data directory as plain JSON so that it can
be inspected, backed up and exported without a database.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

LOCK = threading.RLock()

_UNSAFE = re.compile(r"[^A-Za-z0-9ÄÖÜäöüß._ -]+")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_import_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"IMP-{stamp}-{secrets.token_hex(3).upper()}"


def short_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(4).upper()}"


def safe_filename(name: str, fallback: str = "datei") -> str:
    """Strip path components and characters that are unsafe on Windows/Linux."""
    base = re.split(r"[\\/]", name or "")[-1]
    base = _UNSAFE.sub("_", base).strip(" ._")
    base = re.sub(r"_+", "_", base)
    if not base or base.upper().split(".")[0] in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        base = fallback
    return base[:150]


def write_json_atomic(path: Path, data) -> None:
    """Write JSON via a temp file in the same directory and os.replace()."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_json(path: Path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


class DataDir:
    """Resolves the folders below the application data directory."""

    def __init__(self, root: Path):
        self.root = Path(root)
        for sub in ("imports", "raw", "media", "coverage", "backups", "archive"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

    @property
    def imports(self) -> Path:
        return self.root / "imports"

    @property
    def raw(self) -> Path:
        return self.root / "raw"

    @property
    def media(self) -> Path:
        return self.root / "media"

    @property
    def coverage(self) -> Path:
        return self.root / "coverage"

    @property
    def backups(self) -> Path:
        return self.root / "backups"

    @property
    def archive(self) -> Path:
        return self.root / "archive"

    @property
    def knowledge(self) -> Path:
        return self.root / "knowledge.json"

    @property
    def settings(self) -> Path:
        return self.root / "settings.json"
