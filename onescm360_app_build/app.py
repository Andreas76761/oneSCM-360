"""oneSCM360 Knowledge Studio – local Flask web application.

Runs only on 127.0.0.1. No Entra ID, no Microsoft Graph. OneDrive is treated
as a local sync folder; the cloud status is never faked.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import sys
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from services import claim_service, conflict_service, coverage_service
from services.chapter_service import ChapterError, ChapterService
from services.chat_service import ChatError, ChatService
from services.cleanup_service import CleanupError, CleanupService
from services.manual_service import ManualError, build_manual, safe_stamp, stage_allowed
from services.policy_service import PolicyError, PolicyService, install_network_guard
from services.classification_service import ClassificationError, ClassificationService
from services.export_service import ExportService, table_csv
from services.import_service import LANGUAGES, MAX_BYTES, ImportError_, ImportService
from services.knowledge_service import (CONFLICT_STATUSES, EVIDENCE_STATUSES, VALIDATION_STATUSES,
                                        KnowledgeError, KnowledgeService)
from services.rule_service import CATEGORIES, RuleError, RuleService
from services.storage import DataDir, write_json_atomic

VERSION = "1.0.0"
ROOT = Path(__file__).resolve().parent
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
CSRF_HEADER = "X-oneSCM360"


def create_app(config: dict | None = None) -> Flask:
    config = config or {}
    app = Flask(__name__, static_folder=str(ROOT / "static"), static_url_path="/static")
    app.config["MAX_CONTENT_LENGTH"] = MAX_BYTES + 1024 * 1024  # file limit plus form overhead
    app.config["JSON_SORT_KEYS"] = False
    app.json.ensure_ascii = False
    app.json.sort_keys = False

    data = DataDir(Path(config.get("DATA_DIR") or os.environ.get("ONESCM_DATA_DIR") or ROOT / "data"))
    chapters = ChapterService(Path(config.get("CHAPTERS_DIR") or ROOT / "chapters"), data.root / "chapters", data.backups)
    # The editable rule set lives in data/ so that updating the program (git pull) never touches user edits.
    rules_path = Path(config.get("RULES_PATH") or data.root / "rules.json")
    if not rules_path.exists() and not config.get("RULES_PATH"):
        shutil.copy2(ROOT / "rules.json", rules_path)
    rules = RuleService(rules_path, data.backups)
    knowledge = KnowledgeService(data.knowledge, ROOT / "schemas" / "claim.schema.json", chapters)
    classification = ClassificationService(Path(config.get("CLASSIFICATION_PATH") or ROOT / "classification.json"), chapters)
    imports = ImportService(data, chapters, rules, knowledge, ROOT / "schemas" / "import.schema.json", classification)
    knowledge.role_catalog = classification.role_catalog
    exporter = ExportService(data, config.get("ONEDRIVE_ROOT", os.environ.get("ONESCM_LOCAL_ONEDRIVE_ROOT")))
    app.extensions["onescm"] = {"data": data, "chapters": chapters, "rules": rules, "knowledge": knowledge,
                                "imports": imports, "exporter": exporter}

    # -- security ---------------------------------------------------------------
    @app.before_request
    def guard():
        host = (request.host or "").rsplit(":", 1)[0].strip("[]")
        if host not in LOOPBACK:
            return jsonify(error="Zugriff nur über localhost erlaubt."), 403
        if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get(CSRF_HEADER) != "1":
            return jsonify(error="Anfrage ohne App-Kennung abgelehnt."), 403
        return None

    @app.after_request
    def headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if "Content-Security-Policy" not in response.headers:  # manual previews set a stricter policy themselves
            response.headers["Content-Security-Policy"] = ("default-src 'self'; img-src 'self' data:; style-src 'self'; "
                                                           "script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    # -- error handling ---------------------------------------------------------------
    @app.errorhandler(RequestEntityTooLarge)
    def too_large(_exc):
        return jsonify(error="Die Datei ist größer als 50 MB (Pilotgrenze).", code="TOO_LARGE"), 413

    @app.errorhandler(ImportError_)
    def import_error(exc):
        return jsonify(error=str(exc), code=exc.code), exc.status

    @app.errorhandler(RuleError)
    @app.errorhandler(KnowledgeError)
    @app.errorhandler(ChatError)
    @app.errorhandler(PolicyError)
    @app.errorhandler(ManualError)
    @app.errorhandler(CleanupError)
    def domain_error(exc):
        return jsonify(error=str(exc)), exc.status

    @app.errorhandler(ChapterError)
    @app.errorhandler(ClassificationError)
    def chapter_error(exc):
        return jsonify(error=str(exc)), 400

    @app.errorhandler(HTTPException)
    def http_error(exc):
        return jsonify(error=exc.description or exc.name), exc.code

    @app.errorhandler(Exception)
    def server_error(exc):
        app.logger.exception("Unerwarteter Fehler")
        return jsonify(error="Serverfehler. Bitte Konsole prüfen; es wurde nichts als erfolgreich bestätigt."), 500

    def body() -> dict:
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise KnowledgeError("Ungültiger JSON-Inhalt.")
        return payload

    # -- coverage helper ------------------------------------------------------------
    def compute_coverage(chapter_id: str, persist: bool = True) -> dict:
        chapter = chapters.get(chapter_id)
        kdata = knowledge.load()
        detected = conflict_service.detect(chapter_id, kdata["claims"])
        conflicts = knowledge.store_conflicts(chapter_id, detected)
        problems = knowledge.integrity(chapter_id)
        status: dict[str, str] = {}
        for record in imports.records(chapter_id):
            if record.get("validationStatus") == "BLOCKED" and record.get("status") == "COMPLETED":
                for err in record.get("errors", []):
                    problems.append(f"Import {record['importId']}: {err['message']}")
            for q in record.get("questions", []):
                if q.get("answerStatus") == "ANSWERED" or q["questionId"] not in status:
                    status[q["questionId"]] = q.get("answerStatus", "MISSING")
        for path in data.imports.glob("IMP-*.json"):
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                problems.append(f"{path.name} ist INVALID_JSON.")
        snapshot = coverage_service.calculate(chapter, kdata["claims"], kdata["evidence"], conflicts, problems, status)
        snapshot["questionStatus"] = status
        if persist:
            write_json_atomic(data.coverage / f"{chapter_id}.json", snapshot)
            for record in imports.records(chapter_id):
                gate = "BLOCKED" if record.get("status") == "FAILED" else snapshot["gate"]
                if record.get("gate") != gate:
                    record["gate"] = gate
                    imports.save(record)
        return snapshot

    policy = PolicyService(Path(config.get("REGISTRY_PATH") or ROOT / "tool_registry.json"),
                           Path(config.get("POLICY_PATH") or ROOT / "security_policy.json"),
                           data.root / "audit.jsonl", config.get("USER"))
    if policy.policy.get("external_network") is False and config.get("NETWORK_GUARD", True):
        install_network_guard(policy.policy.get("internal_networks", []))
    app.extensions["onescm"]["policy"] = policy

    def export_chapter(chapter_id: str, parts: str = "package") -> dict:
        chapter = chapters.get(chapter_id)
        records = [r for r in imports.records(chapter_id) if r.get("status") == "COMPLETED"]
        if not records:
            raise ImportError_(f"Für {chapter_id} gibt es keinen abgeschlossenen Import.", 409, "NO_IMPORT")
        snapshot = compute_coverage(chapter_id)
        kdata = knowledge.load()
        chapter_knowledge = {
            "knowledgeBlocks": [k for k in kdata["knowledgeBlocks"] if k["chapterId"] == chapter_id],
            "claims": [c for c in kdata["claims"] if c["chapterId"] == chapter_id],
            "evidence": kdata["evidence"],
            "conflicts": [c for c in kdata["conflicts"] if c["chapterId"] == chapter_id],
        }
        try:
            result = exporter.export_chapter(chapter, records, chapter_knowledge, snapshot, data.raw, parts)
        except PermissionError as exc:
            raise ImportError_(str(exc), 409, "EXPORT_NOT_READY") from exc
        for record in records:
            record["exportedAt"] = result["manifest"]
            imports.save(record)
        return result

    chat = ChatService(data, knowledge, imports, rules, classification, compute_coverage, chapters, policy, export_chapter,
                       ROOT / "chat_eval.json",
                       config.get("ROUTER_URL", os.environ.get("ONESCM_ROUTER_URL", "")),
                       config.get("ROUTER_MODEL", os.environ.get("ONESCM_ROUTER_MODEL", "")))
    app.extensions["onescm"]["chat"] = chat

    # -- pages ---------------------------------------------------------------------------
    @app.get("/")
    def index():
        return send_from_directory(ROOT, "index.html")

    @app.get("/api/meta")
    def meta():
        return jsonify(version=VERSION, chapters=chapters.list(), languages=LANGUAGES,
                       sourceTypes=claim_service.SOURCE_TYPES, ruleCategories=CATEGORIES,
                       evidenceStrengths=claim_service.EVIDENCE_FACTORS, validationStatuses=VALIDATION_STATUSES,
                       evidenceStatuses=EVIDENCE_STATUSES, conflictStatuses=CONFLICT_STATUSES,
                       roles=[{"id": r["id"], "name": r["name"]} for r in classification.role_catalog()],
                       domains=classification.domains(),
                       maxUploadBytes=MAX_BYTES, csrfHeader=CSRF_HEADER)

    @app.get("/api/chapters/<chapter_id>")
    def chapter(chapter_id):
        return jsonify(chapters.get(chapter_id))

    @app.put("/api/chapters/<chapter_id>")
    def chapter_save(chapter_id):
        saved = chapters.save(chapter_id, body(), classification.roles())
        compute_coverage(chapter_id)
        return jsonify(saved)

    @app.delete("/api/chapters/<chapter_id>/override")
    def chapter_reset(chapter_id):
        restored = chapters.reset(chapter_id)
        compute_coverage(chapter_id)
        return jsonify(restored)

    @app.get("/api/chapters/<chapter_id>/questions.csv")
    def chapter_csv(chapter_id):
        return send_file(io.BytesIO(chapters.to_csv(chapter_id)), mimetype="text/csv; charset=utf-8", as_attachment=True,
                         download_name=f"{chapter_id}_Fragenkatalog.csv")

    @app.post("/api/chapters/<chapter_id>/questions.csv")
    def chapter_csv_parse(chapter_id):
        upload = request.files.get("file")
        if not upload:
            return jsonify(error="Bitte eine CSV-Datei auswählen."), 400
        data_bytes = upload.read(1_000_001)
        if len(data_bytes) > 1_000_000:
            return jsonify(error="Die CSV-Datei ist zu groß."), 413
        return jsonify(questions=chapters.parse_csv(chapter_id, data_bytes))

    # -- import ----------------------------------------------------------------------------
    @app.post("/api/import")
    def run_import():
        upload = request.files.get("file")
        content = upload.read() if upload else b""
        record = imports.run(upload.filename if upload else "", content, request.form.get("chapterId", ""),
                             request.form.get("language", ""), request.form.get("sourceType", "ROVO"),
                             force=request.form.get("force") == "1", role=request.form.get("role", ""),
                             domain=request.form.get("domain", ""))
        snapshot = compute_coverage(record["chapterId"])
        record = imports.get(record["importId"]) | ({"duplicate": True} if record.get("duplicate") else {})
        return jsonify(importRecord=record, coverage=snapshot), 200 if record.get("duplicate") else 201

    @app.post("/api/import/classify")
    def classify_import():
        upload = request.files.get("file")
        return jsonify(imports.classify(upload.filename if upload else "", upload.read() if upload else b""))

    @app.get("/api/imports")
    def list_imports():
        return jsonify(imports.list())

    @app.get("/api/imports/<import_id>")
    def get_import(import_id):
        return jsonify(imports.get(import_id))

    @app.delete("/api/imports/<import_id>")
    def delete_import(import_id):
        record_chapter = next((r["chapterId"] for r in imports.list() if r["importId"] == import_id), "")
        result = imports.delete(import_id)
        if record_chapter:
            compute_coverage(record_chapter)
        return jsonify(result)

    @app.post("/api/imports/<import_id>/archive")
    def archive_import(import_id):
        return jsonify(imports.archive(import_id, force=(request.get_json(silent=True) or {}).get("force") is True))

    # -- rules -------------------------------------------------------------------------------
    @app.get("/api/rules")
    def list_rules():
        return jsonify(rules.list())

    @app.post("/api/rules")
    def create_rule():
        return jsonify(rules.create(body())), 201

    @app.put("/api/rules/<rule_id>")
    def update_rule(rule_id):
        return jsonify(rules.update(rule_id, body()))

    @app.delete("/api/rules/<rule_id>")
    def delete_rule(rule_id):
        rules.delete(rule_id)
        return jsonify(deleted=rule_id)

    @app.post("/api/rules/preview")
    def preview_rules():
        normalized, findings = rules.apply(str(body().get("text", ""))[:20000])
        return jsonify(normalizedText=normalized, findings=findings)

    # -- claims & evidence --------------------------------------------------------------
    @app.get("/api/claims")
    def list_claims():
        return jsonify(knowledge.claims(request.args.get("chapterId") or None, request.args.get("status") or None,
                                        request.args.get("questionId") or None))

    @app.post("/api/claims")
    def create_claim():
        claim = knowledge.create_claim(body(), rules.systems())
        compute_coverage(claim["chapterId"])
        return jsonify(claim), 201

    @app.put("/api/claims/<claim_id>")
    def update_claim(claim_id):
        claim = knowledge.update_claim(claim_id, body())
        compute_coverage(claim["chapterId"])
        return jsonify(claim)

    @app.delete("/api/claims/<claim_id>")
    def delete_claim(claim_id):
        chapter_id = next((c["chapterId"] for c in knowledge.claims() if c["claimId"] == claim_id), "")
        knowledge.delete_claim(claim_id)
        if chapter_id:
            compute_coverage(chapter_id)
        return jsonify(deleted=claim_id)

    @app.get("/api/evidence")
    def list_evidence():
        return jsonify(knowledge.evidence(request.args.get("claimId") or None, request.args.get("chapterId") or None))

    def _claim_chapter(claim_id):
        return next((c["chapterId"] for c in knowledge.claims() if c["claimId"] == claim_id), "")

    @app.post("/api/evidence")
    def create_evidence():
        ev = knowledge.create_evidence(body())
        compute_coverage(_claim_chapter(ev["claimId"]))
        return jsonify(ev), 201

    @app.put("/api/evidence/<evidence_id>")
    def update_evidence(evidence_id):
        ev = knowledge.update_evidence(evidence_id, body())
        compute_coverage(_claim_chapter(ev["claimId"]))
        return jsonify(ev)

    @app.delete("/api/evidence/<evidence_id>")
    def delete_evidence(evidence_id):
        claim_id = next((e["claimId"] for e in knowledge.evidence() if e["evidenceId"] == evidence_id), "")
        knowledge.delete_evidence(evidence_id)
        if _claim_chapter(claim_id):
            compute_coverage(_claim_chapter(claim_id))
        return jsonify(deleted=evidence_id)

    @app.get("/api/knowledge-blocks")
    def list_blocks():
        return jsonify(knowledge.knowledge_blocks(request.args.get("chapterId") or None))

    # -- tables ---------------------------------------------------------------------------------
    @app.get("/api/tables")
    def list_tables():
        return jsonify(imports.tables(request.args.get("chapterId") or None))

    @app.get("/api/tables/<table_id>.json")
    def table_json(table_id):
        _, table = imports.table(table_id)
        buffer = io.BytesIO(json.dumps(table, ensure_ascii=False, indent=2).encode("utf-8"))
        return send_file(buffer, mimetype="application/json", as_attachment=True, download_name=f"{table_id}.json")

    @app.get("/api/tables/<table_id>.csv")
    def table_csv_download(table_id):
        _, table = imports.table(table_id)
        return send_file(io.BytesIO(table_csv(table)), mimetype="text/csv; charset=utf-8", as_attachment=True,
                         download_name=f"{table_id}.csv")

    @app.put("/api/tables/<table_id>")
    def update_table(table_id):
        return jsonify(imports.update_table(table_id, body()))

    # -- coverage & conflicts ----------------------------------------------------------------
    @app.get("/api/coverage")
    def coverage_all():
        return jsonify([compute_coverage(c["chapterId"]) for c in chapters.list()])

    @app.get("/api/coverage/<chapter_id>")
    def coverage_one(chapter_id):
        return jsonify(compute_coverage(chapter_id))

    @app.get("/api/conflicts")
    def list_conflicts():
        return jsonify(knowledge.conflicts(request.args.get("chapterId") or None))

    @app.put("/api/conflicts/<conflict_id>")
    def update_conflict(conflict_id):
        conflict = knowledge.update_conflict(conflict_id, body())
        compute_coverage(conflict["chapterId"])
        return jsonify(conflict)

    @app.get("/api/integrity")
    def integrity():
        return jsonify(problems=knowledge.integrity())

    # -- dashboard ---------------------------------------------------------------------------------
    @app.get("/api/dashboard")
    def dashboard():
        rows = imports.list()
        outputs = exporter.outputs()
        return jsonify(
            kpis={"imports": len(rows), "sourceFiles": sum(1 for p in data.raw.iterdir() if p.is_file()),
                  "outputFiles": len(outputs), "json": sum(1 for o in outputs if o["name"].lower().endswith(".json")),
                  "csv": sum(1 for o in outputs if o["name"].lower().endswith(".csv")),
                  "packages": sum(1 for o in outputs if o["name"].lower().endswith(".zip"))},
            imports=rows, outputs=outputs[:200], onedrive=exporter.status())

    # -- synchronisation -------------------------------------------------------------------------
    @app.get("/api/sync/status")
    def sync_status():
        return jsonify(exporter.status())

    @app.post("/api/sync/settings")
    def sync_settings():
        try:
            return jsonify(exporter.set_root(body().get("onedriveRoot", "")))
        except ValueError as exc:
            return jsonify(error=str(exc)), 400

    @app.post("/api/sync/structure")
    def sync_structure():
        try:
            return jsonify(created=exporter.ensure_structure())
        except PermissionError as exc:
            return jsonify(error=str(exc)), 409

    @app.post("/api/sync/export")
    def sync_export():
        return jsonify(export_chapter(body().get("chapterId", ""))), 201

    # -- manual versions (Handbuchstände) ----------------------------------------------------------------
    def manual_for(chapter_id: str, stage: str) -> dict:
        chapter = chapters.get(chapter_id)
        snapshot = compute_coverage(chapter_id)
        ok, reason = stage_allowed(stage, snapshot["gate"])
        if not ok:
            raise ManualError(reason, 400 if stage not in ("Draft", "Reviewed", "Released") else 409)
        kdata = knowledge.load()
        records = imports.records(chapter_id)
        return build_manual(chapter, stage, kdata["claims"], kdata["evidence"],
                            [t for r in records for t in r.get("tables", [])], snapshot, rules.list(), records)

    @app.get("/api/manual/<chapter_id>/preview")
    def manual_preview(chapter_id):
        manual = manual_for(chapter_id, request.args.get("stage", "Draft"))
        response = app.response_class(manual["html"], mimetype="text/html")
        response.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; frame-ancestors 'self'"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        return response

    @app.post("/api/manual/<chapter_id>")
    def manual_generate(chapter_id):
        stage = str(body().get("stage", "Draft"))
        manual = manual_for(chapter_id, stage)
        status = exporter.status()
        if status["localStatus"] != "READY_FOR_CLIENT":
            raise ManualError(f"{status['localStatus']}: {status['reason']}")
        root = Path(status["path"])
        folder = root / "05_Manual_Generated" / stage
        folder.mkdir(parents=True, exist_ok=True)
        base = f"{chapter_id}_{safe_stamp()}_Handbuch_{stage}"
        counter = 1
        while (folder / f"{base}.html").exists():
            counter += 1
            base = f"{chapter_id}_{safe_stamp()}-{counter}_Handbuch_{stage}"
        files = []
        for suffix, content in (("html", manual["html"]), ("md", manual["markdown"])):
            target = folder / f"{base}.{suffix}"
            target.write_text(content, encoding="utf-8")
            files.append(target.relative_to(root).as_posix())
        return jsonify(chapterId=chapter_id, stage=stage, files=files, stats=manual["stats"],
                       cloudStatus=status["cloudStatus"]), 201

    # -- rule-based cleanup ----------------------------------------------------------------------------
    cleanup = CleanupService(Path(config.get("CLEANUP_RULES_PATH") or ROOT / "cleanup_rules.json"), data, imports)

    @app.get("/api/cleanup/preview")
    def cleanup_preview():
        return jsonify(rules=cleanup.rules(), items=cleanup.preview())

    @app.post("/api/cleanup")
    def cleanup_execute():
        payload = body()
        if payload.get("confirm") is not True:
            return jsonify(error="Bereinigung nur mit ausdrücklicher Bestätigung."), 400
        result = cleanup.execute(payload.get("targets"))
        for chapter_info in chapters.list():
            compute_coverage(chapter_info["chapterId"])
        return jsonify(result)

    # -- extracted media -------------------------------------------------------------------------------
    MEDIA_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".bmp": "image/bmp",
                   ".webp": "image/webp", ".svg": "image/svg+xml", ".tif": "image/tiff", ".tiff": "image/tiff",
                   ".emf": "image/emf", ".wmf": "image/wmf"}

    @app.get("/api/media/<import_id>/<name>")
    def media_file(import_id, name):
        record = imports.get(import_id)
        folder = data.media / record["chapterId"] / import_id
        target = (folder / name).resolve()
        if target.parent != folder.resolve() or not target.is_file() or name not in {m["name"] for m in record.get("media", [])}:
            return jsonify(error="Medium nicht gefunden."), 404
        response = send_file(target, mimetype=MEDIA_TYPES.get(target.suffix.lower(), "application/octet-stream"),
                             as_attachment=target.suffix.lower() in (".emf", ".wmf", ".tif", ".tiff", ".svg"), download_name=name)
        response.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'"
        return response

    # -- internal chat bot (router → policy → tool) ---------------------------------------------------
    def chat_session():
        return re.sub(r"[^A-Za-z0-9-]", "", request.headers.get("X-oneSCM360-Session", ""))[:64]

    @app.get("/api/chat/info")
    def chat_info():
        return jsonify(chat.info())

    @app.post("/api/chat")
    def chat_ask():
        payload = body()
        return jsonify(chat.ask(str(payload.get("message", "")), str(payload.get("mode", "rules")), chat_session()))

    @app.post("/api/chat/execute")
    def chat_execute():
        payload = body()
        if payload.get("confirm") is not True:
            return jsonify(error="Ausführung nur mit ausdrücklicher Bestätigung."), 400
        return jsonify(chat.execute_confirmed(str(payload.get("tool", "")), payload.get("arguments") or {}, chat_session()))

    @app.get("/api/chat/audit")
    def chat_audit():
        return jsonify(policy.audit_entries(100))

    @app.post("/api/chat/feedback")
    def chat_feedback():
        return jsonify(chat.feedback(body())), 201

    @app.post("/api/chat/evaluate")
    def chat_evaluate():
        return jsonify(chat.evaluate(str(body().get("mode", "rules"))))

    @app.get("/api/chat/training-data")
    def chat_training_data():
        fmt = request.args.get("format", "notebook")
        if fmt not in ("notebook", "messages"):
            return jsonify(error="Format muss notebook oder messages sein."), 400
        content = chat.training_data(fmt).encode("utf-8")
        return send_file(io.BytesIO(content), mimetype="application/jsonl", as_attachment=True,
                         download_name=f"onescm360_router_{fmt}.jsonl")

    # -- consumption & docs ------------------------------------------------------------------------
    @app.get("/api/consumption/confirmed")
    def confirmed_view():
        kdata = knowledge.load()
        evidence = {}
        for e in kdata["evidence"]:
            if e.get("evidenceStatus") != "REJECTED":
                evidence.setdefault(e["claimId"], []).append(e)
        return jsonify([{**c, "evidence": evidence.get(c["claimId"], [])}
                        for c in kdata["claims"] if c["validationStatus"] == "CONFIRMED"])

    @app.get("/api/docs")
    def docs():
        return jsonify(readme=(ROOT / "README.md").read_text(encoding="utf-8") if (ROOT / "README.md").exists() else "")

    return app


def main():
    host = os.environ.get("ONESCM_HOST", "127.0.0.1")
    if host not in LOOPBACK:
        sys.exit(f"ONESCM_HOST={host} ist nicht erlaubt. Die App läuft ausschließlich auf 127.0.0.1.")
    try:
        port = int(os.environ.get("ONESCM_PORT", "8080"))
    except ValueError:
        sys.exit("ONESCM_PORT muss eine Zahl sein.")
    app = create_app()
    status = app.extensions["onescm"]["exporter"].status()
    print(f"oneSCM360 Knowledge Studio {VERSION}: http://127.0.0.1:{port}\n"
          f"OneDrive-Ziel: {status['path'] or '(nicht konfiguriert)'} → {status['localStatus']}\n"
          f"Cloudstatus: {status['cloudStatus']}\nBeenden mit Strg+C.", flush=True)
    app.run(host="127.0.0.1" if host == "localhost" else host, port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
