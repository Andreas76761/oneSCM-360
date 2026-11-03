"""Internal evidence, document suitability and effective-dated publication rules."""
import re
import hashlib
import json
from datetime import date

DOCUMENTS = ["Handbuch", "Releaseletter", "Quickreference"]
STATES = ["Entwurf", "In Prüfung", "Freigegeben", "Zurückgezogen"]


def iso_date(value, name, optional=True):
    from app import Invalid, clean_text
    value = clean_text(value, name, 10)
    if not value and optional:
        return ""
    try:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError()
    except ValueError as exc:
        raise Invalid(name + " muss YYYY-MM-DD sein.") from exc
    return value


def validate_rules(rows):
    from app import Invalid, clean_text, choice, ROLES
    if not isinstance(rows, list) or len(rows) > 100:
        raise Invalid("Maximal 100 zeitliche Gültigkeitsregeln.")
    result = []
    for r in rows:
        if not isinstance(r, dict):
            raise Invalid("Ungültige Gültigkeitsregel.")
        year = str(r.get("year", "")).strip()
        if year and (not year.isdigit() or not 1900 <= int(year) <= 2200):
            raise Invalid("Jahr muss zwischen 1900 und 2200 liegen oder leer sein.")
        row = {"from": iso_date(r.get("from", ""), "Gültig ab"), "until": iso_date(r.get("until", ""), "Gültig bis"),
               "year": year, "market": clean_text(r.get("market", "*"), "Land", 100).strip() or "*",
               "role": choice(r.get("role", "*"), ["*"] + ROLES, "Rolle"),
               "division": choice(r.get("division", "*"), ["*", "Van", "PC"], "Sparte"),
               "state": choice(r.get("state", "Entwurf"), STATES, "Gültigkeitsstatus"),
               "version": clean_text(r.get("version", ""), "Fachliche Version", 100),
               "environment": choice(r.get("environment", "*"), ["*", "preprod", "prod"], "Umgebung")}
        if row["from"] and row["until"] and row["from"] > row["until"]:
            raise Invalid("Gültig bis liegt vor Gültig ab.")
        result.append(row)
    return result


def validate_evidence(rows):
    from app import Invalid, clean_text, boolean
    if not isinstance(rows, list) or len(rows) > 50:
        raise Invalid("Maximal 50 Jira-Nachweise pro Text.")
    result, seen = [], set()
    for r in rows:
        if not isinstance(r, dict):
            raise Invalid("Ungültiger Jira-Nachweis.")
        key = clean_text(r.get("key", ""), "Jira-Ticket", 100).strip().upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*-\d+", key) or key in seen:
            raise Invalid("Jira-Ticketnummer fehlt, ist ungültig oder doppelt.")
        seen.add(key)
        evidence = {"key": key, "status": clean_text(r.get("status", ""), "Jira-Status", 100).strip(),
                       "type": clean_text(r.get("type", ""), "Jira-Typ", 100).strip(),
                       "date": iso_date(r.get("date", ""), "Ticketdatum"),
                       "verified": boolean(r.get("verified", False), "Nachweis geprüft"),
                       "note": clean_text(r.get("note", ""), "Prüfvermerk", 3000),
                       "content_hash": clean_text(r.get("content_hash", ""), "Prüfstand", 64)}
        if evidence["content_hash"] and not re.fullmatch("[0-9a-f]{64}", evidence["content_hash"]):
            raise Invalid("Ungültiger Prüfstand.")
        if evidence["verified"] and any(not evidence[k] for k in ["status", "type", "date"]):
            raise Invalid("Für einen geprüften Jira-Nachweis Status, Typ und Ticketdatum ergänzen.")
        result.append(evidence)
    return result


def validate_block(b):
    from app import Invalid, boolean
    uses = b.get("uses", {k: True for k in DOCUMENTS})
    if not isinstance(uses, dict) or set(uses) - set(DOCUMENTS):
        raise Invalid("Ungültige Dokumenteignung.")
    result = {"uses": {k: boolean(uses.get(k, False), k) for k in DOCUMENTS},
            "validity": validate_rules(b.get("validity", [])),
            "evidence": validate_evidence(b.get("evidence", []))}
    content = {k: str(b.get(k, "")).strip() for k in ["text", "language", "role", "scope", "market", "division", "release"]}
    content.update(text_format=b.get("text_format", "plain"), uses=result["uses"], validity=result["validity"],
                   variants={k: v.get("text", "").strip() for k, v in b.get("variants", {}).items() if v.get("text", "").strip()})
    for evidence in result["evidence"]:
        fingerprint = hashlib.sha256(json.dumps([content, {k:evidence[k] for k in ["key","status","type","date"]}], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if evidence["verified"] and evidence["content_hash"] and evidence["content_hash"] != fingerprint:
            evidence["verified"] = False
        evidence["content_hash"] = fingerprint if evidence["verified"] else ""
    return result


def effective(rows, p):
    """Only applicable rules compete; greatest specificity wins, equal conflicts block."""
    if not rows:
        return {"matches": True, "state": None, "version": "", "reason": ""}
    at = p.get("as_of", "")
    if not at:
        return {"matches": False, "state": None, "version": "", "reason": "Für zeitlich gesteuerte Inhalte einen Stichtag wählen.", "requires_date": True}
    if p.get("division") == "Beide":
        decisions = [effective(rows, {**p, "division": division}) for division in ["Van", "PC"]]
        if any(r.get("conflict") for r in decisions):
            return {"matches": False, "state": None, "version": "", "reason": "Widersprüchliche zeitliche Gültigkeitsregeln für Van oder PC; bitte auflösen.", "conflict": True}
        if all(not r["matches"] for r in decisions):
            return decisions[0]
        if any(not r["matches"] for r in decisions):
            return {"matches": False, "state": None, "version": "", "reason": "Zeitliche Gültigkeit deckt die kombinierte Ausgabe Van und PC nicht vollständig ab.", "conflict": True}
        if len({(r["state"], r["version"]) for r in decisions}) > 1:
            return {"matches": False, "state": None, "version": "", "reason": "Van und PC haben unterschiedliche Zeitstatus oder Versionen; getrennte Gültigkeitsbereiche verwenden.", "conflict": True}
        return decisions[0]
    scored = []
    for r in rows:
        if r["year"] and r["year"] != at[:4] or r["from"] and at < r["from"] or r["until"] and at > r["until"]:
            continue
        if r["environment"] not in ["*", p.get("environment", "prod")]:
            continue
        if any(r[k] != "*" and r[k] != p[k] and not (k == "division" and p[k] == "Beide") for k in ["market", "role", "division"]):
            continue
        score = sum(r[k] != "*" for k in ["market", "role", "division", "environment"]) + bool(r["year"]) + bool(r["from"]) + bool(r["until"])
        scored.append((score, r))
    if not scored:
        return {"matches": False, "state": None, "version": "", "reason": "Zum Stichtag und Zielprofil nicht gültig."}
    best = max(s for s, _ in scored)
    selected = [r for s, r in scored if s == best]
    # Do not silently choose between equally specific, contradictory release states.
    if len({(r["state"], r["version"]) for r in selected}) > 1:
        return {"matches": False, "state": None, "version": "", "reason": "Widersprüchliche zeitliche Gültigkeitsregeln; bitte auflösen.", "conflict": True}
    r = selected[0]
    return {"matches": r["state"] != "Zurückgezogen", "state": r["state"], "version": r["version"],
            "reason": "Inhalt für dieses Profil zurückgezogen." if r["state"] == "Zurückgezogen" else ""}


def public_text(text, keys):
    for key in sorted(set(keys), key=len, reverse=True):
        boundary = r"(?![\w-])"
        text = re.sub(r"\[[^\]]*\]\(https?://[^\s)]*/browse/" + re.escape(key) + boundary + r"(?:[/?#][^\s)]*)?\)", "", text, flags=re.I)
        text = re.sub(r"https?://[^\s<>\]\)\"]*/browse/" + re.escape(key) + boundary + r"(?:[/?#][^\s<>\]\)\"]*)?", "", text, flags=re.I)
        text = re.sub(r"(?<![\w-])" + re.escape(key) + r"(?![\w-])", "", text, flags=re.I)
    return text


def sanitize_plan(plan, keys):
    """No evidence metadata is placed in reader content, including previews."""
    plan["title"] = public_text(plan["title"], keys)
    plan["warnings"] = [public_text(w, keys) for w in plan["warnings"]]
    plan["metadata"] = {**plan["metadata"], "version": public_text(plan["metadata"]["version"], keys)}
    plan["profile"] = {k: public_text(v,keys) if isinstance(v,str) else v for k,v in plan["profile"].items()}
    for c in plan["chapters"]:
        c["title"] = public_text(c["title"], keys)
        for b in c["blocks"]:
            b["text"] = public_text(b["text"], keys)
            b["source"] = ""  # Source/evidence references are editorial only.
        for f in c.get("figures", []):
            f["title"] = public_text(f["title"], keys)
            for frame in f["frames"]:
                frame["caption"] = public_text(frame["caption"], keys)
    return plan


def matrix(outline):
    import copy
    from app import compose
    plans = {}
    for kind in DOCUMENTS:
        variant = copy.deepcopy(outline)
        variant["metadata"]["document_type"] = kind
        plans[kind] = compose(variant, variant["profile"])
    rows = []
    for chapter in outline["chapters"]:
        for block in chapter["blocks"]:
            states = {}
            for kind, plan in plans.items():
                c = next(c for c in plan["chapters"] if c["id"] == chapter["id"])
                included = any(b.get("id") == block["id"] for b in c["blocks"])
                reason = next((e["reason"] for e in c["excluded"] if e["id"] == block["id"]), "Kapitel durch Profil / Zeitregel ausgeschlossen.")
                states[kind] = {"included": included, "reason": "Wird verwendet" if included else reason}
            rows.append({"chapter": chapter["title"], "id": block["id"], "text": block["text"][:180], "uses": states,
                         "evidence": block.get("evidence", []), "validity": block.get("validity", []), "status": block["status"]})
    return {"rows": rows, "profile": outline["profile"], "warnings": {k: p["warnings"] for k,p in plans.items()}}
