"""Trusted knowledge layer: knowledge blocks, claims, evidence and conflicts."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import jsonschema

from .claim_service import EVIDENCE_FACTORS, SOURCE_TYPES, analyse_statement, evidence_factor
from .storage import LOCK, now_iso, read_json, short_id, write_json_atomic

VALIDATION_STATUSES = ["DRAFT", "REVIEWED", "CONFIRMED", "REJECTED"]
EVIDENCE_STATUSES = ["PROPOSED", "VALIDATED", "REJECTED"]
CONFLICT_STATUSES = ["OPEN", "RESOLVED", "ACCEPTED"]
CLAIM_EDITABLE = ["canonicalStatement", "claimType", "subject", "predicate", "object", "negated", "conditional",
                  "uncertain", "criticality", "division", "role", "market", "pi", "maturity", "tags",
                  "evidenceStatus", "validationStatus", "confidence", "reviewNote", "questionId", "knowledgeId"]
EVIDENCE_EDITABLE = ["claimId", "sourceType", "jiraKey", "sourceTitle", "sourceURL", "sourceDate", "sourceVersion",
                     "evidenceStrength", "evidenceStatus", "excerpt"]


class KnowledgeError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _empty():
    return {"knowledgeBlocks": [], "claims": [], "evidence": [], "conflicts": []}


class KnowledgeService:
    def __init__(self, path: Path, schema_path: Path, chapters):
        self.path = Path(path)
        self.chapters = chapters
        with Path(schema_path).open(encoding="utf-8") as handle:
            self.claim_schema = json.load(handle)
        self.role_catalog = lambda: []  # replaced by the app with the configured role catalog

    # -- persistence -----------------------------------------------------
    def load(self) -> dict:
        try:
            data = read_json(self.path, default=None)
        except json.JSONDecodeError as exc:
            raise KnowledgeError("knowledge.json ist beschädigt (INVALID_JSON).", 500) from exc
        data = data or _empty()
        for key, value in _empty().items():
            data.setdefault(key, value)
        return data

    def save(self, data: dict):
        write_json_atomic(self.path, data)

    # -- import integration ----------------------------------------------
    def add_import(self, bundle: dict):
        with LOCK:
            data = self.load()
            for key in ("knowledgeBlocks", "claims", "evidence"):
                data[key].extend(bundle[key])
            self._refresh_claims(data)
            self.save(data)

    def remove_import(self, import_id: str) -> dict:
        with LOCK:
            data = self.load()
            claim_ids = {c["claimId"] for c in data["claims"] if c.get("sourceImportId") == import_id}
            before = {k: len(data[k]) for k in ("knowledgeBlocks", "claims", "evidence")}
            data["knowledgeBlocks"] = [k for k in data["knowledgeBlocks"] if k.get("sourceImportId") != import_id]
            data["claims"] = [c for c in data["claims"] if c["claimId"] not in claim_ids]
            data["evidence"] = [e for e in data["evidence"] if e["claimId"] not in claim_ids]
            data["conflicts"] = [c for c in data["conflicts"] if not set(c["claimIds"]) & claim_ids]
            self.save(data)
            return {k: before[k] - len(data[k]) for k in before}

    # -- derived fields --------------------------------------------------------
    @staticmethod
    def _refresh_claims(data: dict):
        by_claim: dict[str, list] = {}
        for ev in data["evidence"]:
            by_claim.setdefault(ev["claimId"], []).append(ev)
        for claim in data["claims"]:
            best = max((evidence_factor(e) for e in by_claim.get(claim["claimId"], [])), default=0.0)
            if claim.get("evidenceStatus") == "NOT_RELEVANT" and best > 0:
                continue
            claim["evidenceStatus"] = "EVIDENCED" if best > 0 else "NOT_EVIDENCED"
        KnowledgeService._refresh_blocks(data)

    @staticmethod
    def _refresh_blocks(data: dict):
        """Knowledge block status follows its claims; the version increases when its claims change."""
        claims_by_kb: dict[str, list] = {}
        for claim in data["claims"]:
            claims_by_kb.setdefault(claim["knowledgeId"], []).append(claim)
        for block in data["knowledgeBlocks"]:
            claims = claims_by_kb.get(block["knowledgeId"], [])
            active = [c for c in claims if c["validationStatus"] != "REJECTED"]
            if claims and not active:
                status = "REJECTED"
            elif active and all(c["validationStatus"] == "CONFIRMED" for c in active):
                status = "CONFIRMED"
            elif active and all(c["validationStatus"] in ("REVIEWED", "CONFIRMED") for c in active):
                status = "REVIEWED"
            else:
                status = "DRAFT"
            fingerprint = hashlib.sha1(json.dumps(sorted((c["claimId"], c["canonicalStatement"], c["validationStatus"]) for c in claims),
                                                  ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
            if block.get("fingerprint") and block["fingerprint"] != fingerprint:
                block["version"] = int(block.get("version", 1)) + 1
                block["updatedAt"] = now_iso()
            block["fingerprint"] = fingerprint
            block["validationStatus"] = status

    # -- queries ---------------------------------------------------------------
    def claims(self, chapter_id=None, status=None, question_id=None) -> list[dict]:
        data = self.load()
        factors: dict[str, float] = {}
        for ev in data["evidence"]:
            factors[ev["claimId"]] = max(factors.get(ev["claimId"], 0.0), evidence_factor(ev))
        result = []
        for claim in data["claims"]:
            if chapter_id and claim["chapterId"] != chapter_id:
                continue
            if status and claim["validationStatus"] != status:
                continue
            if question_id and claim["questionId"] != question_id:
                continue
            result.append({**claim, "evidenceFactor": factors.get(claim["claimId"], 0.0)})
        return result

    def evidence(self, claim_id=None, chapter_id=None) -> list[dict]:
        data = self.load()
        chapters = {c["claimId"]: c["chapterId"] for c in data["claims"]}
        return [{**e, "chapterId": chapters.get(e["claimId"], ""), "factor": evidence_factor(e)}
                for e in data["evidence"]
                if (not claim_id or e["claimId"] == claim_id) and (not chapter_id or chapters.get(e["claimId"]) == chapter_id)]

    def knowledge_blocks(self, chapter_id=None) -> list[dict]:
        return [k for k in self.load()["knowledgeBlocks"] if not chapter_id or k["chapterId"] == chapter_id]

    def conflicts(self, chapter_id=None) -> list[dict]:
        return [c for c in self.load()["conflicts"] if not chapter_id or c["chapterId"] == chapter_id]

    # -- validation ------------------------------------------------------------
    def _validate_claim(self, claim: dict, data: dict):
        try:
            jsonschema.validate(claim, self.claim_schema)
        except jsonschema.ValidationError as exc:
            field = "/".join(str(p) for p in exc.absolute_path) or "Claim"
            raise KnowledgeError(f"Ungültiger Claim ({field}): {exc.message}") from exc
        chapter = self.chapters.get(claim["chapterId"])
        if claim["questionId"] not in {q["questionId"] for q in chapter["questions"]}:
            raise KnowledgeError("ChapterId und QuestionId passen nicht zusammen.")
        kb = next((k for k in data["knowledgeBlocks"] if k["knowledgeId"] == claim["knowledgeId"]), None)
        if kb is None:
            raise KnowledgeError("Der Claim verweist auf keinen existierenden Knowledge Block.")
        if kb["chapterId"] != claim["chapterId"] or kb["questionId"] != claim["questionId"]:
            raise KnowledgeError("Knowledge Block gehört zu einem anderen Kapitel bzw. einer anderen Frage.")

    @staticmethod
    def _coerce_claim(payload: dict, base: dict) -> dict:
        claim = dict(base)
        for key in CLAIM_EDITABLE:
            if key in payload:
                claim[key] = payload[key]
        if isinstance(claim.get("pi"), str):
            claim["pi"] = int(claim["pi"]) if claim["pi"].strip().isdigit() else None
        if isinstance(claim.get("tags"), str):
            claim["tags"] = [t.strip() for t in claim["tags"].split(",") if t.strip()]
        for key in ("subject", "predicate", "object", "role", "market", "reviewNote", "canonicalStatement"):
            if key in claim and isinstance(claim[key], str):
                claim[key] = claim[key].strip()
        try:
            claim["confidence"] = float(claim.get("confidence", 0.5))
        except (TypeError, ValueError):
            raise KnowledgeError("Confidence muss eine Zahl zwischen 0 und 1 sein.")
        return claim

    # -- claim CRUD ------------------------------------------------------------
    def create_claim(self, payload: dict, systems: list[str]) -> dict:
        if not isinstance(payload, dict):
            raise KnowledgeError("Ungültiger Claim.")
        chapter_id = payload.get("chapterId", "")
        question_id = payload.get("questionId", "")
        statement = str(payload.get("canonicalStatement", "")).strip()
        if not statement:
            raise KnowledgeError("Die Aussage darf nicht leer sein.")
        chapter = self.chapters.get(chapter_id)
        question = next((q for q in chapter["questions"] if q["questionId"] == question_id), None)
        if question is None:
            raise KnowledgeError("ChapterId und QuestionId passen nicht zusammen.")
        with LOCK:
            data = self.load()
            kid = payload.get("knowledgeId") or ""
            if not kid:
                kb = next((k for k in data["knowledgeBlocks"] if k["questionId"] == question_id and k.get("sourceImportId") == "MANUAL"), None)
                if kb is None:
                    kb = {"knowledgeId": f"KB-{question_id.replace('-', '')}-M{short_id('X')[2:]}", "chapterId": chapter_id,
                          "questionId": question_id, "textDE": "", "textEN": "", "category": chapter["title"],
                          "topic": question["title"], "division": "", "market": "", "validationStatus": "DRAFT",
                          "version": 1, "validity": "", "sourceImportId": "MANUAL"}
                    data["knowledgeBlocks"].append(kb)
                kid = kb["knowledgeId"]
            base = {"claimId": short_id("CLM"), "knowledgeId": kid, "chapterId": chapter_id, "questionId": question_id,
                    "canonicalStatement": statement, **analyse_statement(statement, self.role_catalog() or chapter.get("roles", []), systems),
                    "criticality": question["criticality"], "evidenceStatus": "NOT_EVIDENCED",
                    "validationStatus": "DRAFT", "confidence": 0.5, "sourceImportId": "MANUAL", "reviewNote": ""}
            claim = self._coerce_claim({k: v for k, v in payload.items() if k not in ("chapterId",)}, base)
            claim["knowledgeId"] = kid
            self._validate_claim(claim, data)
            data["claims"].append(claim)
            self._refresh_claims(data)
            self.save(data)
            return claim

    def update_claim(self, claim_id: str, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise KnowledgeError("Ungültiger Claim.")
        with LOCK:
            data = self.load()
            for index, claim in enumerate(data["claims"]):
                if claim["claimId"] == claim_id:
                    updated = self._coerce_claim(payload, claim)
                    if updated["validationStatus"] == "CONFIRMED" and updated.get("uncertain"):
                        raise KnowledgeError("Unsichere Aussagen (möglicherweise, planned …) dürfen nicht als bestätigt gelten. Bitte erst die Aussage präzisieren und „unsicher“ entfernen.")
                    if updated.get("evidenceStatus") == "NOT_RELEVANT" and not any(
                            evidence_factor(e) > 0 for e in data["evidence"] if e["claimId"] == claim_id):
                        raise KnowledgeError("NOT_RELEVANT braucht einen Nachweis. Ohne Nachweis gilt NOT_EVIDENCED.")
                    self._validate_claim(updated, data)
                    updated["updatedAt"] = now_iso()
                    data["claims"][index] = updated
                    self._refresh_claims(data)
                    self.save(data)
                    return updated
        raise KnowledgeError("Claim nicht gefunden.", 404)

    def delete_claim(self, claim_id: str):
        with LOCK:
            data = self.load()
            if not any(c["claimId"] == claim_id for c in data["claims"]):
                raise KnowledgeError("Claim nicht gefunden.", 404)
            data["claims"] = [c for c in data["claims"] if c["claimId"] != claim_id]
            data["evidence"] = [e for e in data["evidence"] if e["claimId"] != claim_id]
            data["conflicts"] = [c for c in data["conflicts"] if claim_id not in c["claimIds"]]
            self._refresh_blocks(data)
            self.save(data)

    # -- evidence CRUD -----------------------------------------------------------
    @staticmethod
    def _clean_evidence(payload: dict, base: dict) -> dict:
        ev = dict(base)
        for key in EVIDENCE_EDITABLE:
            if key in payload:
                ev[key] = str(payload[key]).strip() if payload[key] is not None else ""
        if ev.get("sourceType") not in SOURCE_TYPES:
            raise KnowledgeError("Ungültiger Quelltyp.")
        if ev.get("evidenceStrength") not in EVIDENCE_FACTORS:
            raise KnowledgeError("Ungültige Evidence-Stufe.")
        if ev.get("evidenceStatus") not in EVIDENCE_STATUSES:
            raise KnowledgeError("Ungültiger Evidence-Status.")
        if ev.get("jiraKey") and not re.fullmatch(r"[A-Z][A-Z0-9]{1,9}-\d{1,6}", ev["jiraKey"]):
            raise KnowledgeError("Jira-Key muss dem Muster ABC-123 entsprechen.")
        if ev.get("sourceURL") and not re.match(r"https?://", ev["sourceURL"]):
            raise KnowledgeError("Quell-URL muss mit http:// oder https:// beginnen.")
        if ev["evidenceStrength"] == "DIRECT_VALIDATED" and ev["evidenceStatus"] != "VALIDATED":
            raise KnowledgeError("DIRECT_VALIDATED setzt den Status VALIDATED voraus.")
        for key, limit in (("excerpt", 4000), ("sourceTitle", 300), ("sourceURL", 1000)):
            ev[key] = ev.get(key, "")[:limit]
        return ev

    def create_evidence(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise KnowledgeError("Ungültige Evidence.")
        with LOCK:
            data = self.load()
            if not any(c["claimId"] == payload.get("claimId") for c in data["claims"]):
                raise KnowledgeError("Evidence muss auf einen existierenden Claim verweisen.")
            base = {"evidenceId": short_id("EVD"), "claimId": payload["claimId"], "sourceType": "OTHER", "jiraKey": "",
                    "sourceTitle": "", "sourceURL": "", "sourceDate": "", "sourceVersion": "",
                    "evidenceStrength": "DIRECT", "evidenceStatus": "PROPOSED", "excerpt": "", "sourceImportId": "MANUAL"}
            ev = self._clean_evidence(payload, base)
            data["evidence"].append(ev)
            self._refresh_claims(data)
            self.save(data)
            return ev

    def update_evidence(self, evidence_id: str, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise KnowledgeError("Ungültige Evidence.")
        with LOCK:
            data = self.load()
            for index, ev in enumerate(data["evidence"]):
                if ev["evidenceId"] == evidence_id:
                    updated = self._clean_evidence(payload, ev)
                    if not any(c["claimId"] == updated["claimId"] for c in data["claims"]):
                        raise KnowledgeError("Evidence muss auf einen existierenden Claim verweisen.")
                    data["evidence"][index] = updated
                    self._refresh_claims(data)
                    self.save(data)
                    return updated
        raise KnowledgeError("Evidence nicht gefunden.", 404)

    def delete_evidence(self, evidence_id: str):
        with LOCK:
            data = self.load()
            remaining = [e for e in data["evidence"] if e["evidenceId"] != evidence_id]
            if len(remaining) == len(data["evidence"]):
                raise KnowledgeError("Evidence nicht gefunden.", 404)
            data["evidence"] = remaining
            self._refresh_claims(data)
            self.save(data)

    # -- conflicts ---------------------------------------------------------------
    def store_conflicts(self, chapter_id: str, detected: list[dict]) -> list[dict]:
        with LOCK:
            data = self.load()
            previous = {c["key"]: c for c in data["conflicts"] if c["chapterId"] == chapter_id}
            merged = []
            for conflict in detected:
                old = previous.get(conflict["key"])
                if old:
                    conflict = {**conflict, "conflictId": old["conflictId"], "status": old["status"],
                                "resolutionNote": old.get("resolutionNote", ""), "detectedAt": old["detectedAt"]}
                merged.append(conflict)
            data["conflicts"] = [c for c in data["conflicts"] if c["chapterId"] != chapter_id] + merged
            self.save(data)
            return merged

    def update_conflict(self, conflict_id: str, payload: dict) -> dict:
        status = (payload or {}).get("status")
        if status not in CONFLICT_STATUSES:
            raise KnowledgeError("Konfliktstatus muss OPEN, RESOLVED oder ACCEPTED sein.")
        note = str((payload or {}).get("resolutionNote", "")).strip()[:1000]
        if status != "OPEN" and not note:
            raise KnowledgeError("Bitte eine Begründung für die Auflösung angeben.")
        with LOCK:
            data = self.load()
            for conflict in data["conflicts"]:
                if conflict["conflictId"] == conflict_id:
                    conflict.update(status=status, resolutionNote=note, updatedAt=now_iso())
                    self.save(data)
                    return conflict
        raise KnowledgeError("Konflikt nicht gefunden.", 404)

    # -- integrity -----------------------------------------------------------------
    def integrity(self, chapter_id=None) -> list[str]:
        data = self.load()
        problems = []
        kb = {k["knowledgeId"]: k for k in data["knowledgeBlocks"]}
        claims = {c["claimId"]: c for c in data["claims"]}
        for claim in data["claims"]:
            if chapter_id and claim["chapterId"] != chapter_id:
                continue
            block = kb.get(claim["knowledgeId"])
            if block is None:
                problems.append(f"Claim {claim['claimId']} verweist auf fehlenden Knowledge Block {claim['knowledgeId']}.")
            elif block["questionId"] != claim["questionId"]:
                problems.append(f"Claim {claim['claimId']}: QuestionId passt nicht zum Knowledge Block.")
            if not claim["questionId"].startswith(claim["chapterId"][2:] + "-"):
                problems.append(f"Claim {claim['claimId']}: ChapterId {claim['chapterId']} und QuestionId {claim['questionId']} passen nicht zusammen.")
        for ev in data["evidence"]:
            # Orphaned evidence cannot be attributed to a chapter, so it blocks every chapter.
            if ev["claimId"] not in claims:
                problems.append(f"Evidence {ev['evidenceId']} verweist auf fehlenden Claim {ev['claimId']}.")
        return problems
