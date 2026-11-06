"""Rule-based data cleanup (P1): archive or delete local data after export/review.

Rules live in cleanup_rules.json. Every run is first a dry run (preview); the
execution needs an explicit confirmation and only touches the items of the
preview. Knowledge (claims, evidence) of archived imports stays untouched;
deleting a failed import removes nothing but the failed run.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

ACTIONS = {"archive", "delete", "quarantine", "purge"}


class CleanupError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _age_days(iso: str, now: datetime) -> float | None:
    try:
        created = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return (now - created) / timedelta(days=1)


class CleanupService:
    def __init__(self, rules_path: Path, data_dir, imports):
        self.rules_path = Path(rules_path)
        self.data = data_dir
        self.imports = imports

    def rules(self) -> list[dict]:
        try:
            rules = json.loads(self.rules_path.read_text(encoding="utf-8")).get("rules", [])
        except (OSError, ValueError) as exc:
            raise CleanupError("cleanup_rules.json fehlt oder ist beschädigt.", 500) from exc
        for rule in rules:
            if rule.get("action") not in ACTIONS or not isinstance(rule.get("older_than_days", 0), (int, float)):
                raise CleanupError(f"Bereinigungsregel {rule.get('id')} ist ungültig.", 500)
        return [r for r in rules if r.get("enabled", True)]

    def preview(self, now: datetime | None = None) -> list[dict]:
        now = now or datetime.now(timezone.utc)
        items = []
        listed = self.imports.list()
        for rule in self.rules():
            days = rule.get("older_than_days", 0)
            if rule["action"] == "quarantine":
                for row in listed:
                    if row["status"] == "INVALID_JSON":
                        items.append({"rule": rule["id"], "action": "quarantine", "target": row["importId"], "label": row["file"],
                                      "reason": "Import-JSON beschädigt"})
                continue
            if rule["action"] == "purge":
                for folder in sorted(p for p in self.data.archive.iterdir() if p.is_dir()):
                    age = (now - datetime.fromtimestamp(folder.stat().st_mtime, timezone.utc)) / timedelta(days=1)
                    if age >= days:
                        items.append({"rule": rule["id"], "action": "purge", "target": folder.name, "label": f"Archiv {folder.name}",
                                      "reason": f"seit {age:.0f} Tagen im Archiv"})
                continue
            for row in listed:
                if row["status"] == "INVALID_JSON":
                    continue
                age = _age_days(row.get("createdAt", ""), now)
                if age is None or age < days:
                    continue
                if rule.get("status") and row["status"] != rule["status"]:
                    continue
                if rule.get("exported") is True and not row.get("exportedAt"):
                    continue
                items.append({"rule": rule["id"], "action": rule["action"], "target": row["importId"], "label": row["file"],
                              "reason": f"{row['status']}, {age:.0f} Tage alt" + (", exportiert" if row.get("exportedAt") else "")})
        seen, unique = set(), []
        for item in items:  # one action per target: the first matching rule wins
            if item["target"] not in seen:
                seen.add(item["target"])
                unique.append(item)
        return unique

    def execute(self, targets: list[str], now: datetime | None = None) -> dict:
        if not isinstance(targets, list) or not targets:
            raise CleanupError("Keine Einträge zur Bereinigung ausgewählt.")
        plan = {item["target"]: item for item in self.preview(now)}
        done, skipped = [], []
        for target in targets:
            item = plan.get(target)
            if not item:
                skipped.append({"target": target, "reason": "nicht (mehr) in der Vorschau"})
                continue
            if item["action"] == "archive":
                self.imports.archive(target, force=True)
            elif item["action"] == "delete":
                self.imports.delete(target)
            elif item["action"] == "quarantine":
                folder = self.data.archive / "_invalid"
                folder.mkdir(parents=True, exist_ok=True)
                shutil.move(str(self.data.imports / f"{target}.json"), folder / f"{target}.json")
            elif item["action"] == "purge":
                folder = (self.data.archive / target).resolve()
                if folder.parent != self.data.archive.resolve():
                    skipped.append({"target": target, "reason": "ungültiger Pfad"})
                    continue
                shutil.rmtree(folder)
            done.append(item)
        return {"done": done, "skipped": skipped}
