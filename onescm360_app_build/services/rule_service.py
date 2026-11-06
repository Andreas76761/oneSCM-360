"""Editable rule set persisted in rules.json (CRUD, backup, atomic write)."""
from __future__ import annotations

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .storage import LOCK, read_json, write_json_atomic

CATEGORIES = {
    "naming": "Namenskonvention",
    "system": "Systemübersicht",
    "synonym": "Synonyme",
    "explanation": "Erklärungen",
    "abbreviation": "Abkürzungen",
}
NEEDS_TARGET = {"naming", "synonym", "explanation", "abbreviation"}
MAX_BACKUPS = 30


class RuleError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _pattern(term: str, case_sensitive: bool) -> re.Pattern:
    flags = 0 if case_sensitive else re.IGNORECASE
    # Not inside a word and never part of a Jira key such as ONESCM-123.
    return re.compile(r"(?<![\w-])" + re.escape(term) + r"(?![A-Za-zÄÖÜäöüß]|-\d)", flags)


class RuleService:
    def __init__(self, path: Path, backup_dir: Path):
        self.path = Path(path)
        self.backup_dir = Path(backup_dir)

    # -- persistence -----------------------------------------------------
    def _read(self) -> dict:
        try:
            data = read_json(self.path, default=None)
        except ValueError as exc:  # json.JSONDecodeError
            raise RuleError("rules.json ist beschädigt und kann nicht gelesen werden. Sicherungen liegen unter data/backups.", 500) from exc
        if data is None:
            data = {"version": 1, "rules": []}
        if not isinstance(data, dict) or not isinstance(data.get("rules"), list):
            raise RuleError("rules.json ist beschädigt.", 500)
        return data

    def _backup(self):
        if not self.path.exists():
            return
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        shutil.copy2(self.path, self.backup_dir / f"rules-{stamp}.json")
        backups = sorted(self.backup_dir.glob("rules-*.json"))
        for old in backups[:-MAX_BACKUPS]:
            old.unlink(missing_ok=True)

    def _write(self, data: dict):
        self._backup()
        data["version"] = int(data.get("version", 1))
        write_json_atomic(self.path, data)

    # -- validation ------------------------------------------------------
    @staticmethod
    def _clean(payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise RuleError("Ungültige Regel.")
        category = str(payload.get("category", "")).strip()
        if category not in CATEGORIES:
            raise RuleError("Kategorie ist ungültig.")
        source = re.sub(r"\s+", " ", str(payload.get("source", ""))).strip()
        target = re.sub(r"\s+", " ", str(payload.get("target", ""))).strip()
        note = str(payload.get("note", "")).strip()
        if not source:
            raise RuleError("Der Begriff (Quelle) darf nicht leer sein.")
        if len(source) > 200 or len(target) > 500 or len(note) > 500:
            raise RuleError("Regeltext ist zu lang.")
        if category in NEEDS_TARGET and not target:
            raise RuleError(f"Für {CATEGORIES[category]} ist ein Zielwert erforderlich.")
        if category == "system":
            target = ""
        if category in ("naming", "synonym") and source == target:
            raise RuleError("Quelle und Ziel sind identisch.")
        return {"category": category, "source": source, "target": target, "note": note}

    @staticmethod
    def _duplicate(rules, rule, exclude_id=None) -> bool:
        key = (rule["category"], rule["source"].casefold())
        return any((r["category"], r["source"].casefold()) == key and r["id"] != exclude_id for r in rules)

    # -- CRUD --------------------------------------------------------------
    def list(self) -> list[dict]:
        return self._read()["rules"]

    def create(self, payload: dict) -> dict:
        rule = self._clean(payload)
        with LOCK:
            data = self._read()
            if self._duplicate(data["rules"], rule):
                raise RuleError("Diese Regel existiert bereits (gleiche Kategorie und gleicher Begriff).", 409)
            numbers = [int(r["id"].split("-")[1]) for r in data["rules"] if re.fullmatch(r"R-\d+", r.get("id", ""))]
            rule = {"id": f"R-{(max(numbers) + 1) if numbers else 1:04d}", **rule}
            data["rules"].append(rule)
            self._write(data)
        return rule

    def update(self, rule_id: str, payload: dict) -> dict:
        rule = self._clean(payload)
        with LOCK:
            data = self._read()
            for index, existing in enumerate(data["rules"]):
                if existing["id"] == rule_id:
                    if self._duplicate(data["rules"], rule, exclude_id=rule_id):
                        raise RuleError("Diese Regel existiert bereits (gleiche Kategorie und gleicher Begriff).", 409)
                    data["rules"][index] = {"id": rule_id, **rule}
                    self._write(data)
                    return data["rules"][index]
        raise RuleError("Regel nicht gefunden.", 404)

    def delete(self, rule_id: str) -> None:
        with LOCK:
            data = self._read()
            remaining = [r for r in data["rules"] if r["id"] != rule_id]
            if len(remaining) == len(data["rules"]):
                raise RuleError("Regel nicht gefunden.", 404)
            data["rules"] = remaining
            self._write(data)

    # -- application -------------------------------------------------------
    def systems(self) -> list[str]:
        return [r["source"] for r in self.list() if r["category"] == "system"]

    def apply(self, text: str) -> tuple[str, list[dict]]:
        """Return (normalizedText, findings). The raw text is never modified."""
        rules = self.list()  # re-read on every call: changes apply without restart
        normalized = text
        findings: list[dict] = []
        for rule in rules:
            cat, source, target = rule["category"], rule["source"], rule["target"]
            if cat == "naming":
                pattern = _pattern(source, False)
                hits = [m.group(0) for m in pattern.finditer(normalized) if m.group(0) != target]
                if hits:
                    normalized = pattern.sub(lambda _m: target, normalized)
                    findings.append(self._finding(rule, hits, f"Schreibweise „{hits[0]}“ → „{target}“"))
            elif cat == "synonym":
                pattern = _pattern(source, False)
                hits = [m.group(0) for m in pattern.finditer(normalized)]
                if hits:
                    normalized = pattern.sub(lambda _m: target, normalized)
                    findings.append(self._finding(rule, hits, f"Synonym „{hits[0]}“ → kanonisch „{target}“"))
            elif cat == "abbreviation":
                hits = [m.group(0) for m in _pattern(source, True).finditer(text)]
                if hits:
                    findings.append(self._finding(rule, hits, f"Abkürzung {source} = {target}"))
            elif cat == "explanation":
                hits = [m.group(0) for m in _pattern(source, False).finditer(text)]
                if hits:
                    findings.append(self._finding(rule, hits, f"{source}: {target}"))
            elif cat == "system":
                hits = [m.group(0) for m in _pattern(source, False).finditer(text)]
                if hits:
                    findings.append(self._finding(rule, hits, f"Erlaubtes System erkannt: {source}"))
        return normalized, findings

    @staticmethod
    def _finding(rule, hits, message) -> dict:
        return {"ruleId": rule["id"], "category": rule["category"], "match": hits[0],
                "suggestion": rule["target"], "count": len(hits), "message": message}
