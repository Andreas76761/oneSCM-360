"""Chapter configuration loaded from chapters/CHxx.json (no hard-coded IDs)."""
from __future__ import annotations

import csv
import io
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .storage import LOCK, write_json_atomic

CRITICALITY_WEIGHT = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1, "LOW": 1}
SCHEMA_STATUSES = ["DRAFT", "REFERENCE"]
CSV_COLUMNS = ["QuestionId", "Gruppe", "Titel", "TitleEN", "Kritikalitaet"]
_CHAPTER_ID = re.compile(r"^CH(0[1-9]|1[0-6])$")


class ChapterError(ValueError):
    pass


class ChapterService:
    """Shipped chapter files (chapters/) plus user edits in an override folder (data/chapters/).

    Overrides keep user changes out of the program folder, so updating the app (git pull)
    never conflicts with or overwrites an edited question catalogue.
    """

    def __init__(self, directory: Path, override_dir: Path | None = None, backup_dir: Path | None = None):
        self.directory = Path(directory)
        self.override_dir = Path(override_dir) if override_dir else None
        self.backup_dir = Path(backup_dir) if backup_dir else None

    def _validate(self, cfg: dict, name: str) -> dict:
        cid = cfg.get("chapterId", "")
        if not _CHAPTER_ID.match(cid):
            raise ChapterError(f"Ungültige Kapitelkonfiguration: {name}")
        questions = cfg.get("questions") or []
        expected = [f"{cfg.get('number')}-F{i:02d}" for i in range(1, 21)]
        if cfg.get("number") != cid[2:] or [q.get("questionId") for q in questions] != expected:
            raise ChapterError(f"{name}: Fragen müssen {cid[2:]}-F01 bis {cid[2:]}-F20 lauten.")
        for q in questions:
            if q.get("criticality") not in CRITICALITY_WEIGHT:
                raise ChapterError(f"{name}: ungültige Kritikalität bei {q['questionId']}.")
            if not str(q.get("title", "")).strip():
                raise ChapterError(f"{name}: Titel fehlt bei {q['questionId']}.")
        return cfg

    def _load(self, path: Path) -> dict:
        with path.open("r", encoding="utf-8") as handle:
            cfg = json.load(handle)
        if path.stem != cfg.get("chapterId"):
            raise ChapterError(f"Ungültige Kapitelkonfiguration: {path.name}")
        return self._validate(cfg, path.name)

    def _path(self, chapter_id: str) -> tuple[Path, bool]:
        if self.override_dir:
            override = self.override_dir / f"{chapter_id}.json"
            if override.exists():
                return override, True
        return self.directory / f"{chapter_id}.json", False

    def list(self) -> list[dict]:
        result = []
        for shipped in sorted(self.directory.glob("CH*.json")):
            path, customized = self._path(shipped.stem)
            cfg = self._load(path)
            result.append({k: cfg[k] for k in ("chapterId", "number", "title", "schemaStatus")}
                          | {"focus": cfg.get("focus", ""), "mandatoryEvaluations": cfg.get("mandatoryEvaluations", []),
                             "customized": customized})
        return result

    def get(self, chapter_id: str) -> dict:
        if not isinstance(chapter_id, str) or not _CHAPTER_ID.match(chapter_id):
            raise ChapterError("Kapitel muss CH01 bis CH16 sein.")
        path, customized = self._path(chapter_id)
        if not path.exists():
            raise ChapterError(f"Kapitelkonfiguration {chapter_id} fehlt.")
        return self._load(path) | {"customized": customized}

    def question(self, chapter_id: str, question_id: str) -> dict | None:
        for q in self.get(chapter_id)["questions"]:
            if q["questionId"] == question_id:
                return q
        return None

    # -- editing -----------------------------------------------------------------
    def save(self, chapter_id: str, payload: dict, known_roles: list[str]) -> dict:
        if not self.override_dir:
            raise ChapterError("Kapitel können in dieser Konfiguration nicht bearbeitet werden.")
        current = self.get(chapter_id)
        if not isinstance(payload, dict):
            raise ChapterError("Ungültige Kapitelkonfiguration.")
        clean = lambda v, n: re.sub(r"\s+", " ", str(v or "")).strip()[:n]
        title = clean(payload.get("title", current["title"]), 150)
        if not title:
            raise ChapterError("Der Kapiteltitel darf nicht leer sein.")
        status = payload.get("schemaStatus", current["schemaStatus"])
        if status not in SCHEMA_STATUSES:
            raise ChapterError("Schema-Status muss DRAFT oder REFERENCE sein.")
        roles = payload.get("roles", current.get("roles", []))
        if not isinstance(roles, list) or any(r not in known_roles for r in roles):
            raise ChapterError("Unbekannte Rolle im Kapitel. Rollen werden in classification.json gepflegt.")
        evaluations = payload.get("mandatoryEvaluations", current.get("mandatoryEvaluations", []))
        if isinstance(evaluations, str):
            evaluations = [e for e in (x.strip() for x in evaluations.split(",")) if e]
        questions_in = payload.get("questions", current["questions"])
        if not isinstance(questions_in, list) or len(questions_in) != 20:
            raise ChapterError("Ein Kapitel hat genau 20 Fragen.")
        questions = []
        for index, q in enumerate(questions_in, 1):
            qid = f"{current['number']}-F{index:02d}"
            if not isinstance(q, dict) or q.get("questionId", qid) != qid:
                raise ChapterError(f"Fragekennungen sind fest: erwartet {qid}.")
            questions.append({"questionId": qid, "group": clean(q.get("group"), 100) or "Allgemein",
                              "title": clean(q.get("title"), 200), "titleEn": clean(q.get("titleEn"), 200),
                              "criticality": str(q.get("criticality", "")).upper()})
        cfg = {"chapterId": chapter_id, "number": current["number"], "title": title, "schemaStatus": status,
               "focus": clean(payload.get("focus", current.get("focus", "")), 500),
               "mandatoryEvaluations": [clean(e, 120) for e in evaluations][:20],
               "languages": current.get("languages", ["DE", "EN", "DE+EN"]), "roles": list(dict.fromkeys(roles)),
               "requiredDimensions": current.get("requiredDimensions", []), "questions": questions}
        self._validate(cfg, f"{chapter_id} (Editor)")
        with LOCK:
            self._backup(chapter_id)
            write_json_atomic(self.override_dir / f"{chapter_id}.json", cfg)
        return self.get(chapter_id)

    def reset(self, chapter_id: str) -> dict:
        self.get(chapter_id)
        override = self.override_dir / f"{chapter_id}.json" if self.override_dir else None
        if not override or not override.exists():
            raise ChapterError("Für dieses Kapitel gibt es keine eigenen Änderungen.")
        with LOCK:
            self._backup(chapter_id)
            override.unlink()
        return self.get(chapter_id)

    def _backup(self, chapter_id: str):
        path, customized = self._path(chapter_id)
        if self.backup_dir and customized:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
            shutil.copy2(path, self.backup_dir / f"chapter-{chapter_id}-{stamp}.json")

    # -- CSV ------------------------------------------------------------------------
    def to_csv(self, chapter_id: str) -> bytes:
        cfg = self.get(chapter_id)
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
        writer.writerow(CSV_COLUMNS)
        for q in cfg["questions"]:
            writer.writerow([q["questionId"], q.get("group", ""), q["title"], q.get("titleEn", ""), q["criticality"]])
        return b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8")

    def parse_csv(self, chapter_id: str, data: bytes) -> list[dict]:
        """Parse a question catalogue (semicolon or comma, UTF-8 or Windows-1252) into the 20 questions."""
        cfg = self.get(chapter_id)
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("cp1252")
        if not text.strip():
            raise ChapterError("Die CSV-Datei ist leer.")
        dialect = ";" if text.splitlines()[0].count(";") >= text.splitlines()[0].count(",") else ","
        rows = list(csv.reader(io.StringIO(text), delimiter=dialect))
        header = [h.strip().lower().replace("ä", "ae") for h in rows[0]]
        aliases = {"questionid": ["questionid", "frage", "id", "frage-id", "fragekennung"], "group": ["gruppe", "group", "fragegruppe"],
                   "title": ["titel", "title", "frage-titel", "fragetitel"], "titleEn": ["titleen", "title_en", "titel en", "englisch"],
                   "criticality": ["kritikalitaet", "criticality", "kritisch"]}
        index = {key: next((header.index(a) for a in names if a in header), None) for key, names in aliases.items()}
        if index["title"] is None:
            raise ChapterError("In der CSV fehlt die Spalte „Titel“. Erwartet: " + ";".join(CSV_COLUMNS))
        by_id = {}
        for line, row in enumerate(rows[1:], 2):
            if not any(c.strip() for c in row):
                continue
            get = lambda key: row[index[key]].strip() if index[key] is not None and index[key] < len(row) else ""
            match = re.search(r"F\s*0?(\d{1,2})", get("questionid"), re.I)
            number = int(match.group(1)) if match else len(by_id) + 1
            if not 1 <= number <= 20:
                raise ChapterError(f"Zeile {line}: Frage {number} liegt außerhalb von F01–F20.")
            crit = (get("criticality") or "MEDIUM").upper()
            crit = {"KRITISCH": "CRITICAL", "HOCH": "HIGH", "MITTEL": "MEDIUM", "NIEDRIG": "LOW"}.get(crit, crit)
            if crit not in CRITICALITY_WEIGHT:
                raise ChapterError(f"Zeile {line}: Kritikalität „{crit}“ ist ungültig (CRITICAL, HIGH, MEDIUM, LOW).")
            by_id[number] = {"group": get("group"), "title": get("title"), "titleEn": get("titleEn"), "criticality": crit}
        questions = []
        for n, q in enumerate(cfg["questions"], 1):
            questions.append({**q, **by_id[n]} if n in by_id else q)
        return questions
