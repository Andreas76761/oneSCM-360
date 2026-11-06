"""Chapter configuration loaded from chapters/CHxx.json (no hard-coded IDs)."""
from __future__ import annotations

import json
import re
from pathlib import Path

CRITICALITY_WEIGHT = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1, "LOW": 1}
_CHAPTER_ID = re.compile(r"^CH(0[1-9]|1[0-6])$")


class ChapterError(ValueError):
    pass


class ChapterService:
    def __init__(self, directory: Path):
        self.directory = Path(directory)

    def _load(self, path: Path) -> dict:
        with path.open("r", encoding="utf-8") as handle:
            cfg = json.load(handle)
        cid = cfg.get("chapterId", "")
        if not _CHAPTER_ID.match(cid) or path.stem != cid:
            raise ChapterError(f"Ungültige Kapitelkonfiguration: {path.name}")
        questions = cfg.get("questions") or []
        expected = [f"{cfg['number']}-F{i:02d}" for i in range(1, 21)]
        if [q.get("questionId") for q in questions] != expected:
            raise ChapterError(f"{path.name}: Fragen müssen {expected[0]} bis {expected[-1]} lauten.")
        for q in questions:
            if q.get("criticality") not in CRITICALITY_WEIGHT:
                raise ChapterError(f"{path.name}: ungültige Kritikalität bei {q['questionId']}.")
        return cfg

    def list(self) -> list[dict]:
        result = []
        for path in sorted(self.directory.glob("CH*.json")):
            cfg = self._load(path)
            result.append({k: cfg[k] for k in ("chapterId", "number", "title", "schemaStatus")}
                          | {"focus": cfg.get("focus", ""), "mandatoryEvaluations": cfg.get("mandatoryEvaluations", [])})
        return result

    def get(self, chapter_id: str) -> dict:
        if not isinstance(chapter_id, str) or not _CHAPTER_ID.match(chapter_id):
            raise ChapterError("Kapitel muss CH01 bis CH16 sein.")
        path = self.directory / f"{chapter_id}.json"
        if not path.exists():
            raise ChapterError(f"Kapitelkonfiguration {chapter_id} fehlt.")
        return self._load(path)

    def question(self, chapter_id: str, question_id: str) -> dict | None:
        for q in self.get(chapter_id)["questions"]:
            if q["questionId"] == question_id:
                return q
        return None
