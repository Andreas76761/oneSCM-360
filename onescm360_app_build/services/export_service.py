"""OneDrive folder status and exports (local sync folder only, no Graph)."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import secrets
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .storage import LOCK, now_iso, read_json, safe_filename, write_json_atomic

CLOUD_STATUS = "NOT_VERIFIABLE_WITHOUT_GRAPH"
STRUCTURE = [
    *[f"01_Rovo_Imports/CH{n:02d}" for n in range(1, 17)],
    "02_Jira_Imports", "03_Confluence_Imports", "04_Source_Documents/HTML", "04_Source_Documents/Word",
    "05_Manual_Generated/Draft", "05_Manual_Generated/Reviewed", "05_Manual_Generated/Released",
    "06_Exports/JSON", "06_Exports/CSV", "06_Exports/API", "06_Exports/Packages", "Skill", "Goal", "99_Archive",
]
MAX_LISTED = 2000

KB_FIELDS = ["KnowledgeId", "ChapterId", "QuestionId", "TextDE", "TextEN", "Category", "Topic", "Division", "Market",
             "ValidationStatus", "Version", "Validity", "SourceImportId"]
CLAIM_FIELDS = ["ClaimId", "KnowledgeId", "ChapterId", "QuestionId", "CanonicalStatement", "ClaimType", "Subject",
                "Predicate", "Object", "Criticality", "Division", "Role", "PI", "Maturity", "EvidenceStatus",
                "ValidationStatus", "Confidence"]
EVIDENCE_FIELDS = ["EvidenceId", "ClaimId", "SourceType", "JiraKey", "SourceTitle", "SourceURL", "SourceDate",
                   "SourceVersion", "EvidenceStrength", "EvidenceStatus", "Excerpt"]
COVERAGE_FIELDS = ["SnapshotId", "ChapterId", "CalculatedAt", "QuestionCoverage", "EvidenceCoverage", "RoleCoverage",
                   "DivisionCoverage", "PICoverage", "Confidence", "Readiness", "Konflikte", "Gate", "GateReason"]


def _pascal(key: str) -> str:
    return {"textDE": "TextDE", "textEN": "TextEN", "pi": "PI", "jiraKey": "JiraKey", "sourceURL": "SourceURL"}.get(key, key[:1].upper() + key[1:])


def to_csv(fields: list[str], rows: list[dict]) -> bytes:
    """CSV with UTF-8 BOM and semicolon separator (Excel/SharePoint friendly)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerow(fields)
    for row in rows:
        values = []
        for field in fields:
            value = row.get(field, "")
            if value is None:
                value = ""
            elif isinstance(value, bool):
                value = "true" if value else "false"
            elif isinstance(value, float):
                value = f"{value:.2f}".replace(".", ",")
            text = str(value).replace("\r\n", "\n")
            if text[:1] in ("=", "+", "-", "@") and not text[1:2].isdigit():
                text = "'" + text  # neutralise spreadsheet formula injection
            values.append(text)
        writer.writerow(values)
    return b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8")


def table_csv(table: dict) -> bytes:
    width = table.get("columnCount") or max([len(table.get("header") or [])] + [len(r) for r in table["rows"]] + [1])
    header = list(table.get("header") or []) or [f"Spalte {i + 1}" for i in range(width)]
    header += [f"Spalte {i + 1}" for i in range(len(header), width)]
    rows = [dict(zip(header, list(r) + [""] * (width - len(r)))) for r in table["rows"]]
    return to_csv(header, rows)


class ExportService:
    def __init__(self, data_dir, env_root: str | None):
        self.data = data_dir
        self.env_root = (env_root or "").strip()

    # -- configuration ----------------------------------------------------------
    def root(self) -> tuple[str, str]:
        settings = read_json(self.data.settings, default={}) or {}
        if settings.get("onedriveRoot"):
            return settings["onedriveRoot"], "settings"
        return self.env_root, "ONESCM_LOCAL_ONEDRIVE_ROOT" if self.env_root else "none"

    def set_root(self, path: str | None) -> dict:
        value = (path or "").strip().strip('"')
        if value and not os.path.isabs(value):
            raise ValueError("Bitte einen absoluten Pfad angeben, z. B. C:\\Users\\…\\OneDrive - …\\-oneSCM360.")
        settings = read_json(self.data.settings, default={}) or {}
        settings["onedriveRoot"] = value
        write_json_atomic(self.data.settings, settings)
        return self.status()

    def status(self) -> dict:
        root, origin = self.root()
        result = {"path": root, "configuredBy": origin, "exists": False, "writable": False,
                  "lastLocalChange": None, "cloudStatus": CLOUD_STATUS,
                  "cloudNote": "Die App kann nicht erkennen, ob Dateien in der OneDrive-Cloud angekommen sind. "
                               "Bitte im OneDrive-Client bzw. in der OneDrive-Weboberfläche prüfen."}
        if not root:
            return {**result, "localStatus": "PATH_MISSING", "reason": "Kein OneDrive-Zielpfad konfiguriert."}
        path = Path(root)
        if not path.is_dir():
            return {**result, "localStatus": "PATH_MISSING", "reason": "Der lokale Zielpfad existiert nicht."}
        result["exists"] = True
        probe = path / f".onescm360-write-test-{secrets.token_hex(4)}"
        try:
            probe.write_bytes(b"ok")
            probe.unlink()
            result["writable"] = True
        except OSError as exc:
            return {**result, "localStatus": "NOT_READY", "reason": f"Lokaler Schreibtest fehlgeschlagen: {exc.strerror or exc}"}
        latest = None
        for count, file in enumerate(self._walk(path)):
            if count >= MAX_LISTED * 5:
                break
            try:
                mtime = file.stat().st_mtime
            except OSError:
                continue
            latest = max(latest or mtime, mtime)
        result["lastLocalChange"] = datetime.fromtimestamp(latest, timezone.utc).replace(microsecond=0).isoformat() if latest else None
        return {**result, "localStatus": "READY_FOR_CLIENT",
                "reason": "Lokaler Ordner vorhanden und beschreibbar. Das ist keine Bestätigung der Cloud-Synchronisation."}

    @staticmethod
    def _walk(root: Path):
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for name in filenames:
                if not name.startswith(".onescm360-write-test"):
                    yield Path(dirpath) / name

    def _ready_root(self) -> Path:
        status = self.status()
        if status["localStatus"] != "READY_FOR_CLIENT":
            raise PermissionError(f"{status['localStatus']}: {status['reason']}")
        return Path(status["path"])

    def ensure_structure(self) -> list[str]:
        root = self._ready_root()
        created = []
        for rel in STRUCTURE:
            folder = root / rel
            if not folder.exists():
                folder.mkdir(parents=True, exist_ok=True)
                created.append(rel)
        return created

    def outputs(self) -> list[dict]:
        root, _ = self.root()
        if not root or not Path(root).is_dir():
            return []
        rows = []
        for file in self._walk(Path(root)):
            try:
                stat = file.stat()
            except OSError:
                continue
            rows.append({"name": file.name, "path": file.relative_to(root).as_posix(), "size": stat.st_size,
                         "modifiedAt": datetime.fromtimestamp(stat.st_mtime, timezone.utc).replace(microsecond=0).isoformat()})
            if len(rows) >= MAX_LISTED:
                break
        return sorted(rows, key=lambda r: r["modifiedAt"], reverse=True)

    # -- export --------------------------------------------------------------------
    def export_chapter(self, chapter: dict, imports: list[dict], knowledge: dict, coverage: dict, raw_dir: Path) -> dict:
        with LOCK:
            root = self._ready_root()
            self.ensure_structure()
            cid = chapter["chapterId"]
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            prefix = f"{cid}_{stamp}"
            written: list[Path] = []

            def write(rel: str, content: bytes):
                target = root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp = target.with_name(f".tmp-{target.name}")
                tmp.write_bytes(content)
                os.replace(tmp, target)
                written.append(target)

            # Raw source files
            for record in imports:
                raw = raw_dir / record.get("rawFile", "")
                if not record.get("rawFile") or not raw.is_file():
                    continue
                folder = {"ROVO": f"01_Rovo_Imports/{cid}", "JIRA": "02_Jira_Imports", "CONFLUENCE": "03_Confluence_Imports"}.get(
                    record.get("sourceType"), "04_Source_Documents/Word" if record["sourceFile"]["type"] == "docx" else "04_Source_Documents/HTML")
                write(f"{folder}/{safe_filename(raw.name)}", raw.read_bytes())

            claim_ids = {c["claimId"] for c in knowledge["claims"]}
            tables = [t for r in imports for t in r.get("tables", [])]
            payload = {
                "exportedAt": now_iso(), "chapter": {k: chapter[k] for k in ("chapterId", "title", "schemaStatus")},
                "imports": [{k: r.get(k) for k in ("importId", "status", "validationStatus", "language", "sourceType", "role", "domain", "domainName", "sourceFile", "createdAt")} for r in imports],
                "knowledgeBlocks": knowledge["knowledgeBlocks"], "claims": knowledge["claims"],
                "evidence": [e for e in knowledge["evidence"] if e["claimId"] in claim_ids],
                "conflicts": knowledge["conflicts"], "coverage": coverage, "tables": tables,
                "cloudStatus": CLOUD_STATUS,
            }
            json_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            write(f"06_Exports/JSON/{prefix}_export.json", json_bytes)
            write(f"06_Exports/API/{prefix}_confirmed.json", json.dumps(
                [c for c in knowledge["claims"] if c["validationStatus"] == "CONFIRMED"], ensure_ascii=False, indent=2).encode("utf-8"))

            def rows(items):
                return [{_pascal(k): v for k, v in item.items()} for item in items]
            cov_row = {"SnapshotId": coverage["snapshotId"], "ChapterId": cid, "CalculatedAt": coverage["calculatedAt"],
                       "QuestionCoverage": coverage["questionCoverage"], "EvidenceCoverage": coverage["evidenceCoverage"],
                       "RoleCoverage": coverage["roleCoverage"], "DivisionCoverage": coverage["divisionCoverage"],
                       "PICoverage": coverage["piCoverage"], "Confidence": coverage["confidence"],
                       "Readiness": coverage["readiness"], "Konflikte": coverage["conflicts"], "Gate": coverage["gate"],
                       "GateReason": coverage["gateReason"]}
            write(f"06_Exports/CSV/{prefix}_KnowledgeBlocks.csv", to_csv(KB_FIELDS, rows(knowledge["knowledgeBlocks"])))
            write(f"06_Exports/CSV/{prefix}_Claims.csv", to_csv(CLAIM_FIELDS, rows(knowledge["claims"])))
            write(f"06_Exports/CSV/{prefix}_Evidence.csv", to_csv(EVIDENCE_FIELDS, rows(payload["evidence"])))
            write(f"06_Exports/CSV/{prefix}_Coverage.csv", to_csv(COVERAGE_FIELDS, [cov_row]))
            for table in tables:
                write(f"06_Exports/CSV/{prefix}_{table['tableId']}.csv", table_csv(table))
                write(f"06_Exports/JSON/{prefix}_{table['tableId']}.json", json.dumps(table, ensure_ascii=False, indent=2).encode("utf-8"))

            manifest = {
                "manifestVersion": 1, "chapterId": cid, "createdAt": now_iso(), "cloudStatus": CLOUD_STATUS,
                "note": "Lokale Bereitstellung im OneDrive-Sync-Ordner. SharePoint-Transfer erfolgt manuell.",
                "files": [{"path": p.relative_to(root).as_posix(), "size": p.stat().st_size,
                           "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in written],
            }
            manifest_rel = f"06_Exports/{prefix}_manifest.json"
            write(manifest_rel, json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                for path in written:
                    if "/06_Exports/" in "/" + path.relative_to(root).as_posix():
                        archive.write(path, path.relative_to(root).as_posix())
            zip_rel = f"06_Exports/Packages/{prefix}_upload.zip"
            write(zip_rel, zip_buffer.getvalue())
            return {"chapterId": cid, "root": str(root), "manifest": manifest_rel, "package": zip_rel,
                    "files": [p.relative_to(root).as_posix() for p in written], "cloudStatus": CLOUD_STATUS}
