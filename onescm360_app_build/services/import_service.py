"""End-to-end import: file → parser → tables → rules → questions → claims."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

import jsonschema

from . import claim_service
from .docx_parser import parse_docx
from .html_parser import ParseError, parse_html
from .storage import LOCK, now_iso, new_import_id, read_json, safe_filename, write_json_atomic

ALLOWED_TYPES = {"docx", "html", "htm"}
LANGUAGES = ["DE", "EN", "DE+EN"]
MAX_BYTES = 50 * 1024 * 1024
# Tolerant question markers: "F01", "01 F01", "01-F01", "CH01-F01", "01_F1", "F 01:".
QUESTION_RE = re.compile(r"^\s*(?:(?:CH\s*)?(\d{1,2})\s*[-–_.\s]\s*)?F\s*-?\s*(\d{1,2})(?!\d)(?:\s*[:.)\-–]\s*|\s+|$)", re.I)
NOT_RELEVANT_RE = re.compile(r"\b(nicht relevant|not relevant|n/a|entfällt)\b", re.I)
NO_INFO_RE = re.compile(r"\b(keine informationen?|no information|nicht bekannt|unknown|unbekannt)\b", re.I)


class ImportError_(ValueError):
    def __init__(self, message: str, status: int = 400, code: str = "INVALID"):
        super().__init__(message)
        self.status = status
        self.code = code


def file_type(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


class ImportService:
    def __init__(self, data_dir, chapters, rules, knowledge, schema_path: Path):
        self.data = data_dir
        self.chapters = chapters
        self.rules = rules
        self.knowledge = knowledge
        with Path(schema_path).open(encoding="utf-8") as handle:
            self.schema = json.load(handle)

    # -- listing -----------------------------------------------------------
    def list(self) -> list[dict]:
        result = []
        for path in sorted(self.data.imports.glob("IMP-*.json"), reverse=True):
            try:
                record = read_json(path)
                if not isinstance(record, dict) or "importId" not in record:
                    raise ValueError("kein Importobjekt")
                result.append({
                    "importId": record["importId"], "chapterId": record.get("chapterId", ""),
                    "file": record.get("sourceFile", {}).get("name", ""), "status": record.get("status", ""),
                    "validationStatus": record.get("validationStatus", ""), "language": record.get("language", ""),
                    "sourceType": record.get("sourceType", ""),
                    "questions": sum(1 for q in record.get("questions", []) if q.get("answerStatus") == "ANSWERED"),
                    "tables": len(record.get("tables", [])), "createdAt": record.get("createdAt", ""),
                    "exportedAt": record.get("exportedAt", ""), "gate": record.get("gate", ""),
                })
            except (OSError, ValueError, json.JSONDecodeError):
                result.append({"importId": path.stem, "chapterId": "", "file": path.name, "status": "INVALID_JSON",
                               "validationStatus": "BLOCKED", "gate": "BLOCKED", "questions": 0, "tables": 0,
                               "createdAt": "", "exportedAt": "", "language": "", "sourceType": ""})
        return result

    def get(self, import_id: str) -> dict:
        if not re.fullmatch(r"IMP-[0-9]{8}-[0-9]{6}-[A-F0-9]{6}", import_id or ""):
            raise ImportError_("Ungültige Import-ID.", 404)
        path = self.data.imports / f"{import_id}.json"
        if not path.exists():
            raise ImportError_("Import nicht gefunden.", 404)
        try:
            return read_json(path)
        except json.JSONDecodeError as exc:
            raise ImportError_("Import-JSON ist beschädigt (INVALID_JSON).", 500, "INVALID_JSON") from exc

    def records(self, chapter_id=None) -> list[dict]:
        out = []
        for path in self.data.imports.glob("IMP-*.json"):
            try:
                record = read_json(path)
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(record, dict) and (not chapter_id or record.get("chapterId") == chapter_id):
                out.append(record)
        return sorted(out, key=lambda r: r.get("createdAt", ""))

    def save(self, record: dict):
        write_json_atomic(self.data.imports / f"{record['importId']}.json", record)

    # -- validation of the upload --------------------------------------------
    def validate_upload(self, filename: str, data: bytes, chapter_id: str, language: str, source_type: str):
        name = safe_filename(filename or "")
        ftype = file_type(name)
        if not filename:
            raise ImportError_("Bitte eine Datei auswählen.", 400, "NO_FILE")
        if ftype not in ALLOWED_TYPES:
            raise ImportError_(f"Dateityp „.{ftype or '?'}“ wird nicht unterstützt. Erlaubt sind .docx, .html und .htm.", 415, "WRONG_TYPE")
        if not data:
            raise ImportError_("Die Datei ist leer.", 400, "EMPTY")
        if len(data) > MAX_BYTES:
            raise ImportError_("Die Datei ist größer als 50 MB (Pilotgrenze).", 413, "TOO_LARGE")
        self.chapters.get(chapter_id)
        if language not in LANGUAGES:
            raise ImportError_("Sprache muss DE, EN oder DE+EN sein.")
        if source_type not in claim_service.SOURCE_TYPES:
            raise ImportError_("Ungültiger Quelltyp.")
        return name, ftype

    # -- main entry --------------------------------------------------------------
    def run(self, filename: str, data: bytes, chapter_id: str, language: str, source_type: str = "ROVO",
            force: bool = False) -> dict:
        name, ftype = self.validate_upload(filename, data, chapter_id, language, source_type)
        digest = hashlib.sha256(data).hexdigest()
        with LOCK:
            existing = next((r for r in self.records(chapter_id)
                             if r.get("sourceFile", {}).get("sha256") == digest and r.get("language") == language
                             and r.get("sourceType") == source_type and r.get("status") == "COMPLETED"), None)
            if existing and not force:
                return {**existing, "duplicate": True}
            import_id = existing["importId"] if existing else new_import_id()
            if existing:
                self.knowledge.remove_import(import_id)
            record = {
                "importId": import_id, "chapterId": chapter_id, "language": language, "sourceType": source_type,
                "sourceFile": {"name": name, "type": ftype, "size": len(data), "sha256": digest},
                "status": "RECEIVED", "validationStatus": "", "journal": (existing or {}).get("journal", []),
                "questions": [], "tables": [], "media": [], "findings": [], "errors": [], "warnings": [],
                "createdAt": (existing or {}).get("createdAt") or now_iso(),
            }
            if existing:
                record["journal"].append({"status": "REPROCESSED", "at": now_iso()})
            self._step(record, "RECEIVED")
            raw_path = self.data.raw / f"{import_id}_{name}"
            raw_path.write_bytes(data)
            record["rawFile"] = raw_path.name
            try:
                parsed = parse_docx(data) if ftype == "docx" else parse_html(data)
                self._step(record, "PARSED")
                self._analyse(record, parsed)
                self._step(record, "ANALYZED")
                bundle = claim_service.build_from_import(record, self.chapters.get(chapter_id), self.rules.systems(), source_type)
                record["counts"] = {k: len(v) for k, v in bundle.items()}
                jsonschema.validate(record, self.schema)
                self.knowledge.add_import(bundle)
                self._step(record, "COMPLETED")
            except ParseError as exc:
                return self._fail(record, str(exc), 422, "PARSE_ERROR")
            except jsonschema.ValidationError as exc:
                return self._fail(record, f"Import entspricht nicht dem Schema: {exc.message}", 500, "SCHEMA")
            except ImportError_ as exc:
                return self._fail(record, str(exc), exc.status, exc.code)
            except Exception as exc:  # noqa: BLE001 - journal every unexpected failure
                return self._fail(record, f"Interner Fehler bei der Verarbeitung ({type(exc).__name__}).", 500, "SERVER_ERROR")
            self.save(record)
            return record

    def _step(self, record, status):
        record["status"] = status
        record["journal"].append({"status": status, "at": now_iso()})
        self.save(record)

    def _fail(self, record, message, status, code):
        record["errors"].append({"code": code, "message": message})
        record["validationStatus"] = "BLOCKED"
        record["gate"] = "BLOCKED"
        self._step(record, "FAILED")
        raise ImportError_(message, status, code)

    # -- analysis ---------------------------------------------------------------
    def _analyse(self, record: dict, parsed: dict):
        chapter = self.chapters.get(record["chapterId"])
        number = chapter["number"]
        known = {q["questionId"]: q for q in chapter["questions"]}
        segments: dict[str, dict] = {}
        order: list[str] = []
        current = None
        preamble = []
        table_seq = self._next_table_number(record["chapterId"], record["importId"])
        has_content = False
        for block in parsed["blocks"]:
            if block["kind"] == "table":
                has_content = True
                table_seq += 1
                header = block["rows"][0] if block.get("hasHeader") else []
                body = block["rows"][1:] if block.get("hasHeader") else block["rows"]
                width = max(len(r) for r in block["rows"])
                record["tables"].append({
                    "tableId": f"TBL-{record['chapterId']}-{table_seq:03d}", "importId": record["importId"],
                    "chapterId": record["chapterId"], "sourceQuestionId": current,
                    "reviewRequired": current is None, "header": header, "rows": body,
                    "columnCount": width, "rowCount": len(body),
                    "unevenRows": any(len(r) != width for r in block["rows"]),
                })
                continue
            text = block["text"]
            has_content = has_content or bool(text.strip())
            match = QUESTION_RE.match(text)
            if match and match.group(2):
                prefix, qnum = match.group(1), int(match.group(2))
                qid = f"{number}-F{qnum:02d}"
                rest = text[match.end():].strip()
                if prefix is not None and int(prefix) != int(number):
                    record["errors"].append({"code": "CHAPTER_MISMATCH",
                                             "message": f"„{text[:40]}“ gehört zu Kapitel {int(prefix):02d}, importiert wird {record['chapterId']}."})
                    current = None
                    continue
                if qid not in known:
                    record["warnings"].append(f"Fragekennung „{match.group(0).strip()}“ liegt außerhalb von F01–F20 und wurde ignoriert.")
                    current = None
                    continue
                current = qid
                if qid not in segments:
                    segments[qid] = {"questionText": "", "lines": []}
                    order.append(qid)
                else:
                    record["warnings"].append(f"{qid} kommt mehrfach vor; die Abschnitte wurden zusammengeführt.")
                if rest:
                    # "F04: Was …?" or a short heading such as "F04 Rollen" is the question title, not the answer.
                    is_title = rest.endswith("?") or (len(rest.split()) <= 6 and not rest.rstrip().endswith((".", "!", ";")))
                    if is_title and not segments[qid]["questionText"]:
                        segments[qid]["questionText"] = rest
                    else:
                        segments[qid]["lines"].append(rest)
                continue
            if current:
                segments[current]["lines"].append(text)
            else:
                preamble.append(text)
        if not has_content:
            raise ImportError_("Das Dokument enthält keinen lesbaren Inhalt.", 422, "NO_CONTENT")
        if not segments and not record["tables"]:
            raise ImportError_(f"Keine Fragen {number}-F01 bis {number}-F20 im Dokument gefunden.", 422, "NO_QUESTIONS")
        if preamble:
            record["warnings"].append(f"{len(preamble)} Zeile(n) vor der ersten Frage wurden nicht zugeordnet.")
        all_findings: dict[str, dict] = {}
        for qid in sorted(known):
            seg = segments.get(qid)
            raw = "\n".join(seg["lines"]).strip() if seg else ""
            normalized, findings = self.rules.apply(raw) if raw else ("", [])
            for f in findings:
                agg = all_findings.setdefault(f["ruleId"], {**f, "count": 0, "questions": []})
                agg["count"] += f["count"]
                agg["questions"].append(qid)
            if not seg:
                status = "MISSING"
            elif not raw:
                status = "EMPTY"
            elif NOT_RELEVANT_RE.search(raw) and len(raw.split()) < 6:
                status = "NOT_RELEVANT"
            elif NO_INFO_RE.search(raw) and len(raw.split()) < 8:
                status = "NOT_EVIDENCED"
            else:
                status = "ANSWERED"
            record["questions"].append({
                "questionId": qid, "title": known[qid]["title"], "criticality": known[qid]["criticality"],
                "questionText": seg["questionText"] if seg else "", "text": raw, "normalizedText": normalized,
                "answerStatus": status, "ruleFindings": [f["ruleId"] for f in findings],
            })
        record["findings"] = list(all_findings.values())
        if record["errors"]:
            record["validationStatus"] = "BLOCKED"
        elif record["warnings"] or any(t["reviewRequired"] for t in record["tables"]):
            record["validationStatus"] = "WARNINGS"
        else:
            record["validationStatus"] = "VALID"
        for item in parsed.get("media", []):
            folder = self.data.media / record["chapterId"] / record["importId"]
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / safe_filename(item["name"], "bild")
            target.write_bytes(item["data"])
            record["media"].append({"name": target.name, "size": len(item["data"])})

    def _next_table_number(self, chapter_id: str, import_id: str) -> int:
        highest = 0
        for record in self.records(chapter_id):
            if record.get("importId") == import_id:
                continue
            for table in record.get("tables", []):
                try:
                    highest = max(highest, int(table["tableId"].rsplit("-", 1)[-1]))
                except (KeyError, ValueError):
                    continue
        return highest

    # -- tables ---------------------------------------------------------------------
    def tables(self, chapter_id=None) -> list[dict]:
        return [t for r in self.records(chapter_id) for t in r.get("tables", [])]

    def table(self, table_id: str) -> tuple[dict, dict]:
        for record in self.records():
            for table in record.get("tables", []):
                if table["tableId"] == table_id:
                    return record, table
        raise ImportError_("Tabelle nicht gefunden.", 404)

    def update_table(self, table_id: str, payload: dict) -> dict:
        with LOCK:
            record, table = self.table(table_id)
            qid = (payload or {}).get("sourceQuestionId")
            if qid in ("", None):
                table["sourceQuestionId"] = None
                table["reviewRequired"] = True
            else:
                chapter = self.chapters.get(record["chapterId"])
                if qid not in {q["questionId"] for q in chapter["questions"]}:
                    raise ImportError_("Die Frage gehört nicht zum Kapitel der Tabelle.")
                table["sourceQuestionId"] = qid
                table["reviewRequired"] = not bool((payload or {}).get("reviewed", True))
            self.save(record)
            return table

    # -- cleanup ---------------------------------------------------------------------
    def archive(self, import_id: str, force: bool = False) -> dict:
        with LOCK:
            record = self.get(import_id)
            if not record.get("exportedAt") and not force:
                raise ImportError_("Nur exportierte Importe werden archiviert. Erst exportieren oder bewusst erzwingen.", 409)
            target = self.data.archive / import_id
            target.mkdir(parents=True, exist_ok=True)
            shutil.move(str(self.data.imports / f"{import_id}.json"), target / f"{import_id}.json")
            raw = self.data.raw / record.get("rawFile", "")
            if record.get("rawFile") and raw.exists():
                shutil.move(str(raw), target / raw.name)
            return {"archived": import_id, "folder": str(target)}

    def delete(self, import_id: str) -> dict:
        with LOCK:
            path = self.data.imports / f"{import_id}.json"
            if not re.fullmatch(r"IMP-[0-9]{8}-[0-9]{6}-[A-F0-9]{6}", import_id or "") or not path.exists():
                raise ImportError_("Import nicht gefunden.", 404)
            try:
                record = read_json(path)
            except json.JSONDecodeError:
                record = {}
            removed = self.knowledge.remove_import(import_id)
            path.unlink()
            raw = self.data.raw / (record.get("rawFile") or "")
            if record.get("rawFile") and raw.is_file():
                raw.unlink()
            media = self.data.media / (record.get("chapterId") or "_") / import_id
            if media.is_dir():
                shutil.rmtree(media)
            return {"deleted": import_id, **removed}
