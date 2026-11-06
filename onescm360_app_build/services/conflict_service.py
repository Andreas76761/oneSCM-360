"""Conflict detection between claims of one chapter (section 7).

Different scope (role, division, market, PI) is not automatically a conflict;
only claims whose comparable fields line up are checked.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib

from .claim_service import APPROVAL_PREDICATES, RESTRICT

PRODUCTIVE = "PRODUCTION"
NON_PRODUCTIVE = {"IN_TEST", "IMPLEMENTED", "ACCEPTED"}


def _tokens(claim) -> set[str]:
    return set((claim.get("object") or "").split())


def _similar(a, b, threshold=0.5) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    if not ta and not tb:
        return True  # nothing beyond subject/predicate: the subject carries the topic
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= threshold


def _same(a, b, key) -> bool:
    return (a.get(key) or "").casefold() == (b.get(key) or "").casefold() if key != "pi" else a.get("pi") == b.get("pi")


def _subject(claim) -> str:
    return (claim.get("subject") or "").casefold()


def _conflict(chapter_id, ctype, severity, a, b, description) -> dict:
    ids = sorted([a["claimId"], b["claimId"]])
    key = hashlib.sha1(f"{ctype}|{'|'.join(ids)}".encode()).hexdigest()[:16]
    return {"conflictId": f"CNF-{key[:8].upper()}", "key": key, "chapterId": chapter_id, "type": ctype,
            "severity": severity, "claimIds": ids, "description": description, "status": "OPEN",
            "resolutionNote": "", "detectedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat()}


def detect(chapter_id: str, claims: list[dict]) -> list[dict]:
    active = [c for c in claims if c["chapterId"] == chapter_id and c["validationStatus"] != "REJECTED"]
    found: dict[str, dict] = {}

    def add(conflict):
        found.setdefault(conflict["key"], conflict)

    for i, a in enumerate(active):
        for b in active[i + 1:]:
            same_pred = bool(a.get("predicate")) and a.get("predicate") == b.get("predicate")
            similar = _similar(a, b)
            same_scope = all(_same(a, b, k) for k in ("role", "division", "market", "pi"))
            critical = "CRITICAL" in (a.get("criticality"), b.get("criticality"))
            if _subject(a) and _subject(a) == _subject(b) and same_pred and similar:
                if a.get("negated") != b.get("negated") and not (a.get("conditional") or b.get("conditional")) and same_scope:
                    add(_conflict(chapter_id, "DIRECT_CONTRADICTION", "CRITICAL", a, b,
                                  f"„{a['canonicalStatement']}“ widerspricht „{b['canonicalStatement']}“."))
                ma, mb = a.get("maturity"), b.get("maturity")
                if same_scope and {ma, mb} & {PRODUCTIVE} and {ma, mb} & NON_PRODUCTIVE:
                    add(_conflict(chapter_id, "MATURITY_CONFLICT", "CRITICAL", a, b,
                                  f"Gleicher Scope gleichzeitig {ma} und {mb}."))
                if (ma and ma == mb and a.get("pi") is not None and b.get("pi") is not None and a["pi"] != b["pi"]
                        and _same(a, b, "division") and _same(a, b, "role") and a.get("negated") == b.get("negated")):
                    add(_conflict(chapter_id, "PI_CONFLICT", "MAJOR", a, b,
                                  f"Gleiche Funktion und Reifestufe {ma} in PI{a['pi']} und PI{b['pi']}."))
                divisions = {a.get("division"), b.get("division")}
                if ("BOTH" in divisions and divisions & {"PC", "VAN"} and a.get("negated") == b.get("negated")
                        and _same(a, b, "pi") and any(RESTRICT.search(c["canonicalStatement"]) for c in (a, b))):
                    add(_conflict(chapter_id, "DIVISION_CONFLICT", "MAJOR", a, b,
                                  "Funktion gilt laut einer Aussage für BOTH, laut der anderen nur für eine Division."))
            if (same_pred and a.get("predicate") in APPROVAL_PREDICATES and similar and a.get("role") and b.get("role")
                    and not _same(a, b, "role") and not a.get("negated") and not b.get("negated") and _same(a, b, "division")):
                add(_conflict(chapter_id, "ROLE_CONFLICT", "CRITICAL" if critical else "MAJOR", a, b,
                              f"{a['role']} und {b['role']} genehmigen laut Aussagen denselben Vorgang."))
            if (a.get("claimType") == b.get("claimType") == "SOURCE_SYSTEM" and _subject(a) != _subject(b)
                    and similar and not a.get("negated") and not b.get("negated")
                    and _same(a, b, "division") and _same(a, b, "market")):
                add(_conflict(chapter_id, "SOURCE_SYSTEM_CONFLICT", "CRITICAL", a, b,
                              f"Unterschiedliche datenführende Systeme: {a['subject']} und {b['subject']}."))
    return list(found.values())
