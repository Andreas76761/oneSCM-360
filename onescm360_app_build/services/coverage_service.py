"""Coverage dimensions, readiness score and hard gates (section 8)."""
from __future__ import annotations

import re

from .chapter_service import CRITICALITY_WEIGHT
from .claim_service import evidence_factor
from .storage import now_iso, short_id

WEIGHTS = {"questions": 0.20, "evidence": 0.30, "roles": 0.15, "division": 0.15, "pi": 0.10, "confidence": 0.10}
DIRECT_THRESHOLD = 0.9
PERMISSION_RE = re.compile(r"\b(darf|dürfen|kann|können|berechtig\w*|may|can|allowed|permitted)\b", re.I)
RESTRICTION_RE = re.compile(r"\b(nicht|kein\w*|nur|ausschließlich|not|only|cannot|never)\b", re.I)


def _gate(readiness, evidence, critical_questions_ok, critical_claims_ok, blockers) -> tuple[str, str]:
    if blockers:
        return "BLOCKED", f"{len(blockers)} Hard Blocker: " + "; ".join(blockers[:3])
    if readiness >= 90 and evidence >= 90 and critical_questions_ok and critical_claims_ok:
        return "READY", "Alle READY-Schwellen erfüllt."
    if readiness >= 70:
        missing = []
        if readiness < 90:
            missing.append("Readiness < 90")
        if evidence < 90:
            missing.append("Evidence < 90")
        if not critical_questions_ok:
            missing.append("kritische Fragen nicht vollständig")
        if not critical_claims_ok:
            missing.append("kritische Claims nicht vollständig belegt")
        return "REVIEW", "Für READY fehlt: " + ", ".join(missing) if missing else "Review erforderlich."
    if readiness >= 40:
        return "INCOMPLETE", "Readiness zwischen 40 und 70."
    if readiness > 0:
        return "STARTED", "Readiness unter 40."
    return "NOT_STARTED", "Noch keine verwertbaren Inhalte."


def calculate(chapter: dict, claims: list[dict], evidence: list[dict], conflicts: list[dict],
              integrity_problems: list[str], question_status: dict[str, str]) -> dict:
    chapter_id = chapter["chapterId"]
    claims = [c for c in claims if c["chapterId"] == chapter_id and c["validationStatus"] != "REJECTED"]
    by_claim: dict[str, list] = {}
    for ev in evidence:
        by_claim.setdefault(ev["claimId"], []).append(ev)
    factor = {c["claimId"]: max((evidence_factor(e) for e in by_claim.get(c["claimId"], [])), default=0.0) for c in claims}

    # Questions (criticality-weighted answer status)
    claims_by_q: dict[str, list] = {}
    for c in claims:
        claims_by_q.setdefault(c["questionId"], []).append(c)
    q_total = q_score = 0.0
    critical_q_total = critical_q_done = 0
    for q in chapter["questions"]:
        weight = CRITICALITY_WEIGHT[q["criticality"]]
        # A question counts once it has at least one active claim. A bare
        # "nicht relevant" without a supporting statement yields no claim and
        # therefore stays NOT_EVIDENCED.
        answered = bool(claims_by_q.get(q["questionId"]))
        q_total += weight
        q_score += weight * (1.0 if answered else 0.0)
        if q["criticality"] == "CRITICAL":
            critical_q_total += 1
            critical_q_done += 1 if answered else 0
    questions = q_score / q_total if q_total else 0.0

    # Evidence (criticality-weighted evidence per claim)
    e_total = sum(CRITICALITY_WEIGHT[c["criticality"]] for c in claims)
    evidence_score = (sum(CRITICALITY_WEIGHT[c["criticality"]] * factor[c["claimId"]] for c in claims) / e_total) if e_total else 0.0

    # Roles: purpose, permission, actions, restriction, division, evidence
    role_scores = []
    role_details = {}
    for role in chapter.get("roles", []):
        rc = [c for c in claims if (c.get("role") or "").casefold() == role.casefold()]
        checks = {
            "Zweck": bool(rc),
            "Berechtigung": any(c["claimType"] == "PERMISSION" or PERMISSION_RE.search(c["canonicalStatement"]) for c in rc),
            "Aktionen": any(c.get("predicate") and c["predicate"] not in ("ist", "wird", "hat") for c in rc),
            "Einschränkung": any(c.get("negated") or RESTRICTION_RE.search(c["canonicalStatement"]) for c in rc),
            "Division": any(c.get("division") for c in rc),
            "Evidence": any(factor[c["claimId"]] >= DIRECT_THRESHOLD for c in rc),
        }
        role_details[role] = checks
        role_scores.append(sum(checks.values()) / len(checks))
    roles = sum(role_scores) / len(role_scores) if role_scores else 0.0

    # PC/VAN: separately confirmed coverage; PC evidence never counts for VAN
    def division_score(name):
        relevant = [c for c in claims if c.get("division") in (name, "BOTH")]
        if any(factor[c["claimId"]] >= DIRECT_THRESHOLD for c in relevant):
            return 1.0
        return 0.5 if relevant else 0.0
    division = (division_score("PC") + division_score("VAN")) / 2

    # PI: historical stages PI0-16 plus planning PI17/18
    historical = [c for c in claims if c.get("pi") is not None and c["pi"] <= 16]
    planned = [c for c in claims if c.get("pi") is not None and c["pi"] >= 17]
    hist_score = 1.0 if any(c.get("maturity") for c in historical) else 0.5 if historical else 0.0
    plan_score = 1.0 if planned else 0.0
    pi = (hist_score + plan_score) / 2

    # Confidence: evidence, consistency, validation, recency, source independence
    open_conflicts = [c for c in conflicts if c["chapterId"] == chapter_id and c["status"] == "OPEN"]
    if claims:
        conflicted = {cid for c in open_conflicts for cid in c["claimIds"]}
        consistency = 1 - len(conflicted & set(factor)) / len(claims)
        validation = sum(1 for c in claims if c["validationStatus"] in ("REVIEWED", "CONFIRMED")) / len(claims)
        claim_evidence = [e for c in claims for e in by_claim.get(c["claimId"], []) if e.get("evidenceStatus") != "REJECTED"]
        recency = (sum(1 for e in claim_evidence if e["evidenceStrength"] != "OUTDATED") / len(claim_evidence)) if claim_evidence else 0.0
        independent = sum(1 for c in claims if len({e["sourceType"] for e in by_claim.get(c["claimId"], []) if evidence_factor(e) > 0}) >= 2
                          or any(e["sourceType"] != "ROVO" and evidence_factor(e) > 0 for e in by_claim.get(c["claimId"], []))) / len(claims)
        confidence = (evidence_score + consistency + validation + recency + independent) / 5
    else:
        consistency = validation = recency = independent = confidence = 0.0

    dims = {"questions": questions, "evidence": evidence_score, "roles": roles, "division": division, "pi": pi, "confidence": confidence}
    readiness = round(sum(dims[k] * WEIGHTS[k] for k in WEIGHTS) * 100, 1)
    dims_pct = {k: round(v * 100, 1) for k, v in dims.items()}

    # Hard blockers
    blockers = []
    for conflict in open_conflicts:
        if conflict["severity"] == "CRITICAL":
            label = "Widersprüchlicher Produktivstatus" if conflict["type"] == "MATURITY_CONFLICT" else "Offener kritischer Konflikt"
            blockers.append(f"{label} {conflict['conflictId']} ({conflict['type']})")
    for c in claims:
        unresolved = c["validationStatus"] != "CONFIRMED"
        if c["criticality"] == "CRITICAL" and factor[c["claimId"]] < DIRECT_THRESHOLD:
            blockers.append(f"Kritischer Claim ohne direkte Evidence: {c['claimId']}")
        tags = set(c.get("tags") or [])
        if unresolved and "permission" in tags and c["criticality"] == "CRITICAL":
            blockers.append(f"Ungeklärte kritische Berechtigung: {c['claimId']}")
        if unresolved and "financial" in tags:
            blockers.append(f"Ungeklärte finanzielle Regel: {c['claimId']}")
        if unresolved and "irreversible" in tags:
            blockers.append(f"Ungeklärte irreversible Aktion: {c['claimId']}")
        if unresolved and "security" in tags:
            blockers.append(f"Security/Compliance ungeklärt: {c['claimId']}")
    blockers.extend(f"Referentielle Integrität: {p}" for p in integrity_problems)

    critical_claims = [c for c in claims if c["criticality"] == "CRITICAL"]
    critical_claims_ok = all(factor[c["claimId"]] >= DIRECT_THRESHOLD for c in critical_claims)
    critical_questions_ok = critical_q_done == critical_q_total
    gate, reason = _gate(readiness, dims_pct["evidence"], critical_questions_ok, critical_claims_ok, blockers)
    return {
        "snapshotId": short_id("COV"), "chapterId": chapter_id, "calculatedAt": now_iso(),
        "questionCoverage": dims_pct["questions"], "evidenceCoverage": dims_pct["evidence"],
        "roleCoverage": dims_pct["roles"], "divisionCoverage": dims_pct["division"], "piCoverage": dims_pct["pi"],
        "confidence": dims_pct["confidence"], "readiness": readiness, "conflicts": len(open_conflicts),
        "gate": gate, "gateReason": reason, "blockers": blockers,
        "details": {
            "weights": WEIGHTS, "claims": len(claims), "criticalQuestions": f"{critical_q_done}/{critical_q_total}",
            "criticalClaimsEvidenced": f"{sum(1 for c in critical_claims if factor[c['claimId']] >= DIRECT_THRESHOLD)}/{len(critical_claims)}",
            "roles": role_details, "confidenceParts": {"evidence": round(evidence_score * 100, 1), "consistency": round(consistency * 100, 1),
                                                         "validation": round(validation * 100, 1), "recency": round(recency * 100, 1),
                                                         "independence": round(independent * 100, 1)},
        },
    }
