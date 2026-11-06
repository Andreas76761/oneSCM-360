"""Rule-based preparation of atomic claims and evidence from answer text.

Everything produced here is a *proposal*: claims start as DRAFT and must be
reviewed manually. Uncertain wording is never turned into confirmed facts.
"""
from __future__ import annotations

import re

from .storage import short_id

EVIDENCE_FACTORS = {
    "DIRECT_VALIDATED": 1.00,
    "MULTIPLE_CONSISTENT": 1.00,
    "DIRECT": 0.90,
    "INDIRECT": 0.50,
    "OUTDATED": 0.25,
    "CONFLICTING": 0.00,
    "MISSING": 0.00,
}
SOURCE_TYPES = ["ROVO", "JIRA", "CONFLUENCE", "HTML", "WORD", "OTHER"]
IMPORT_SOURCE_STRENGTH = {"ROVO": "INDIRECT", "JIRA": "DIRECT", "CONFLUENCE": "DIRECT",
                          "HTML": "INDIRECT", "WORD": "INDIRECT", "OTHER": "INDIRECT"}

NEGATION = re.compile(r"\b(nicht|kein|keine|keinen|keinem|keiner|niemals|nie|not|no|never|cannot|can't|won't|isn't|aren't|doesn't|don't)\b", re.I)
CONDITION = re.compile(r"\b(wenn|falls|sofern|sobald|solange|vorausgesetzt|if|unless|provided|as long as|when)\b", re.I)
UNCERTAIN = re.compile(r"\b(möglicherweise|eventuell|evtl\.?|voraussichtlich|vermutlich|wahrscheinlich|geplant|angedacht|unklar|offen|tbd|expected|planned|may|might|possibly|probably|likely|presumably|unclear)\b", re.I)
RESTRICT = re.compile(r"\b(nur|ausschließlich|lediglich|only|exclusively)\b", re.I)
PI_RE = re.compile(r"\bPI\s*-?\s*(\d{1,2})\b")
JIRA_KEY = re.compile(r"\b([A-Z][A-Z0-9]{1,9}-\d{1,6})\b")
URL_RE = re.compile(r"https?://[^\s<>\"')]+")
MATURITY_PATTERNS = [
    ("IN_TEST", re.compile(r"\b(im test|in test|in testing|testphase|uat|in_test)\b", re.I)),
    ("ACCEPTED", re.compile(r"\b(abgenommen|accepted)\b", re.I)),
    ("IMPLEMENTED", re.compile(r"\b(umgesetzt|implementiert|implemented|entwickelt|developed)\b", re.I)),
    ("PLANNED", re.compile(r"\b(geplant|planned|roadmap|vorgesehen)\b", re.I)),
]
PRODUCTION = re.compile(r"\b(produktiv|in produktion|production|productive|live|go-live|im betrieb)\b", re.I)
PC_RE = re.compile(r"\b(PC|Pkw|PKW|Passenger Cars?)\b")
VAN_RE = re.compile(r"\b(VAN|Vans?|Transporter)\b")
BOTH_RE = re.compile(r"\b(beide Divisionen|both divisions|BOTH)\b")
MARKET_RE = re.compile(r"\b(?:Markt|Market|im Markt|in the market)\s+([A-ZÄÖÜ][\wÄÖÜäöüß-]{1,30})")
SOURCE_SYSTEM_RE = re.compile(r"\b(datenführend\w*|führende[sn]? System|leading system|master system|source of truth|system of record)\b", re.I)

MODALS = {"darf": "darf", "dürfen": "darf", "kann": "kann", "können": "kann", "muss": "muss", "müssen": "muss",
          "may": "darf", "can": "kann", "must": "muss", "soll": "soll", "sollen": "soll", "should": "soll"}
VERBS = {
    "genehmigt": "genehmigen", "genehmigen": "genehmigen", "approves": "genehmigen", "approve": "genehmigen",
    "freigeben": "freigeben", "gibt frei": "freigeben", "releases": "freigeben", "release": "freigeben",
    "storniert": "stornieren", "stornieren": "stornieren", "cancels": "stornieren", "cancel": "stornieren",
    "erstellt": "erstellen", "erstellen": "erstellen", "creates": "erstellen", "create": "erstellen", "anlegen": "erstellen", "legt an": "erstellen",
    "prüft": "prüfen", "prüfen": "prüfen", "checks": "prüfen", "check": "prüfen", "validates": "prüfen",
    "bearbeitet": "bearbeiten", "bearbeiten": "bearbeiten", "ändert": "ändern", "ändern": "ändern", "edits": "ändern", "edit": "ändern", "changes": "ändern",
    "löscht": "löschen", "löschen": "löschen", "deletes": "löschen", "delete": "löschen",
    "sieht": "sehen", "sehen": "sehen", "sees": "sehen", "see": "sehen", "views": "sehen",
    "übermittelt": "übermitteln", "übermitteln": "übermitteln", "sendet": "übermitteln", "sends": "übermitteln", "send": "übermitteln",
    "liefert": "liefern", "liefern": "liefern", "provides": "liefern", "provide": "liefern",
    "bestellt": "bestellen", "bestellen": "bestellen", "orders": "bestellen", "order": "bestellen",
    "synchronisiert": "synchronisieren", "synchronizes": "synchronisieren",
    "berechnet": "berechnen", "berechnen": "berechnen", "calculates": "berechnen",
    "unterstützt": "unterstützen", "unterstützen": "unterstützen", "supports": "unterstützen",
    "verwaltet": "verwalten", "verwalten": "verwalten", "manages": "verwalten",
}
COPULA = {"ist": "ist", "sind": "ist", "wird": "wird", "werden": "wird", "is": "ist", "are": "ist", "hat": "hat", "haben": "hat", "has": "hat", "have": "hat"}
APPROVAL_PREDICATES = {"genehmigen", "freigeben"}
STOPWORDS = set("der die das den dem des ein eine einen einem einer und oder im in am an auf für mit von zu zum zur bei aus nach über unter vor ist sind wird werden "
                "the a an and or of to in on for with by from at is are be as it this that diese dieser dieses auch noch bereits "
                # Scope words (division, restriction) are compared separately, not as part of the object.
                "pc van vans pkw transporter both beide divisionen nur ausschließlich lediglich only exclusively seit since ab "
                # Maturity words are compared via the maturity field.
                "produktiv produktion production productive live betrieb test testing testphase uat umgesetzt implementiert implemented "
                "entwickelt developed abgenommen accepted geplant planned roadmap vorgesehen".split())
TAG_PATTERNS = {
    "permission": re.compile(r"\b(berechtig\w*|zugriffsrecht\w*|permission\w*|authori[sz]\w*|rolle\w*|darf|dürfen|may)\b", re.I),
    "financial": re.compile(r"\b(preis\w*|price\w*|pricing|rechnung\w*|invoice\w*|zahlung\w*|payment\w*|steuer\w*|tax\w*|währung\w*|currenc\w*|kosten|cost\w*|finanz\w*|financ\w*|gutschrift\w*|credit note\w*|rabatt\w*|discount\w*)\b", re.I),
    "irreversible": re.compile(r"\b(lösch\w*|delet\w*|storn\w*|cancel\w*|irreversib\w*|endgültig\w*|unwiderruflich\w*|permanent\w*)\b", re.I),
    "security": re.compile(r"\b(security|sicherheit\w*|datenschutz\w*|dsgvo|gdpr|compliance|passwor\w*|verschlüssel\w*|encrypt\w*|personenbezogen\w*|personal data)\b", re.I),
}
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ0-9\"„(])")


def _words(text: str) -> list[str]:
    return re.findall(r"[\wÄÖÜäöüß'-]+", text)


def object_tokens(text: str) -> set[str]:
    tokens = set()
    for w in _words(text.lower()):
        if w in STOPWORDS or w in MODALS or w in VERBS or w in COPULA or NEGATION.fullmatch(w) or len(w) < 3:
            continue
        tokens.add(re.sub(r"(en|er|es|e|n|s)$", "", w) or w)
    return tokens


def split_sentences(text: str) -> list[str]:
    sentences = []
    for line in text.split("\n"):
        line = line.strip(" -•*\t")
        if not line:
            continue
        sentences.extend(s.strip() for s in _SENTENCE_SPLIT.split(line) if s.strip())
    return sentences


def split_conjunctions(sentence: str, roles: list[str]) -> list[str]:
    """Split coordinated statements unless the sentence is conditional."""
    if CONDITION.search(sentence):
        return [sentence]
    parts = [p.strip(" ,;") for p in re.split(r"\s*;\s*", sentence) if p.strip(" ,;")]
    result = []
    role_re = re.compile("|".join(re.escape(r) for r in roles), re.I) if roles else None
    for part in parts:
        pieces = re.split(r",?\s+(?:und|sowie|and|as well as)\s+", part)
        if len(pieces) < 2:
            result.append(part)
            continue
        current = pieces[0]
        for piece in pieces[1:]:
            distinct = (_has_verb(piece) or (role_re and role_re.search(piece)) or PI_RE.search(piece)
                        or PC_RE.search(piece) or VAN_RE.search(piece) or _maturity(piece))
            if distinct and len(_words(piece)) >= 3 and len(_words(current)) >= 3:
                result.append(current.strip())
                current = piece
            else:
                current = f"{current} und {piece}"
        result.append(current.strip())
    return result


def _has_verb(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(r"\b" + re.escape(v) + r"\b", lowered) for v in list(VERBS) + list(MODALS))


def _maturity(text: str) -> str:
    for name, pattern in MATURITY_PATTERNS:
        if pattern.search(text):
            return name
    if PRODUCTION.search(text) and not NEGATION.search(text):
        return "PRODUCTION"
    return ""


def _division(text: str) -> str:
    pc, van = bool(PC_RE.search(text)), bool(VAN_RE.search(text))
    if BOTH_RE.search(text) or (pc and van):
        return "BOTH"
    return "PC" if pc else "VAN" if van else ""


def analyse_statement(text: str, roles: list[str], systems: list[str]) -> dict:
    lowered = text.lower()
    role = next((r for r in roles if re.search(r"(?<!\w)" + re.escape(r) + r"(?!\w)", text, re.I)), "")
    system = next((s for s in systems if re.search(r"(?<!\w)" + re.escape(s) + r"(?!\w)", text, re.I)), "")
    modal = next((MODALS[w] for w in _words(lowered) if w in MODALS), "")
    verb = ""
    for phrase, lemma in sorted(VERBS.items(), key=lambda kv: -len(kv[0])):
        if re.search(r"\b" + re.escape(phrase) + r"\b", lowered):
            verb = lemma
            break
    if not verb:
        verb = next((COPULA[w] for w in _words(lowered) if w in COPULA), "")
    source_system = bool(SOURCE_SYSTEM_RE.search(text))
    predicate = "datenführend" if source_system else verb or modal
    subject = role or system
    if source_system and system:
        subject = system
    if not subject:
        words = _words(text)
        subject = " ".join(words[:3]) if words else ""
    obj_text = text
    for remove in filter(None, [subject, role, system]):
        obj_text = re.sub(re.escape(remove), " ", obj_text, flags=re.I)
    obj_text = SOURCE_SYSTEM_RE.sub(" ", obj_text)
    obj_text = PI_RE.sub(" ", obj_text)
    obj = " ".join(sorted(object_tokens(obj_text)))[:500]
    pi_match = PI_RE.search(text)
    maturity = _maturity(text)
    negated = bool(NEGATION.search(text))
    uncertain = bool(UNCERTAIN.search(text))
    tags = [name for name, pattern in TAG_PATTERNS.items() if pattern.search(text)]
    if source_system:
        claim_type = "SOURCE_SYSTEM"
    elif maturity == "PLANNED" or (uncertain and pi_match and int(pi_match.group(1)) >= 17):
        claim_type = "PLAN"
    elif modal in ("darf", "kann") or "permission" in tags and modal:
        claim_type = "PERMISSION"
    elif maturity:
        claim_type = "STATUS"
    elif RESTRICT.search(text) or negated:
        claim_type = "RESTRICTION"
    elif verb and verb not in ("ist", "wird", "hat"):
        claim_type = "PROCESS"
    else:
        claim_type = "FACT"
    market = MARKET_RE.search(text)
    return {
        "claimType": claim_type, "subject": subject[:200], "predicate": predicate[:200], "object": obj,
        "negated": negated, "conditional": bool(CONDITION.search(text)), "uncertain": uncertain,
        "restricted": bool(RESTRICT.search(text)), "division": _division(text), "role": role,
        "market": market.group(1) if market else "", "pi": int(pi_match.group(1)) if pi_match else None,
        "maturity": maturity, "tags": tags,
    }


def evidence_factor(evidence: dict) -> float:
    if evidence.get("evidenceStatus") == "REJECTED":
        return 0.0
    return EVIDENCE_FACTORS.get(evidence.get("evidenceStrength", "MISSING"), 0.0)


def build_from_import(record: dict, chapter: dict, systems: list[str], source_type: str) -> dict:
    """Create knowledge blocks, claims and evidence proposals for one import."""
    roles = chapter.get("roles", [])
    criticality = {q["questionId"]: q["criticality"] for q in chapter["questions"]}
    blocks, claims, evidence = [], [], []
    base_strength = IMPORT_SOURCE_STRENGTH.get(source_type, "INDIRECT")
    for question in record["questions"]:
        if question.get("answerStatus") != "ANSWERED" or question.get("blocked"):
            continue
        qid = question["questionId"]
        kid = f"KB-{qid.replace('-', '')}-{short_id('X')[2:]}"
        statements = []
        for sentence in split_sentences(question["normalizedText"]):
            if sentence.rstrip().endswith("?"):
                continue
            statements.extend(s for s in split_conjunctions(sentence, roles) if len(_words(s)) >= 3)
        if not statements:
            continue
        lang = record["language"]
        blocks.append({
            "knowledgeId": kid, "chapterId": record["chapterId"], "questionId": qid,
            "textDE": question["normalizedText"] if lang in ("DE", "DE+EN") else "",
            "textEN": question["normalizedText"] if lang in ("EN", "DE+EN") else "",
            "category": chapter.get("title", ""), "topic": question.get("title", ""),
            "division": "", "market": "", "validationStatus": "DRAFT", "version": 1,
            "validity": "", "sourceImportId": record["importId"],
        })
        divisions = set()
        for statement in statements:
            analysis = analyse_statement(statement, roles, systems)
            divisions.add(analysis["division"])
            claim_id = short_id("CLM")
            claim = {
                "claimId": claim_id, "knowledgeId": kid, "chapterId": record["chapterId"], "questionId": qid,
                "canonicalStatement": statement[:4000], **analysis,
                "criticality": criticality.get(qid, "MEDIUM"),
                "evidenceStatus": "EVIDENCED", "validationStatus": "DRAFT",
                "confidence": 0.3 if analysis["uncertain"] else 0.5,
                "sourceImportId": record["importId"], "reviewNote": "",
            }
            claims.append(claim)
            evidence.append({
                "evidenceId": short_id("EVD"), "claimId": claim_id, "sourceType": source_type, "jiraKey": "",
                "sourceTitle": record["sourceFile"]["name"], "sourceURL": "", "sourceDate": record["createdAt"][:10],
                "sourceVersion": "", "evidenceStrength": base_strength, "evidenceStatus": "PROPOSED",
                "excerpt": statement[:1000], "sourceImportId": record["importId"],
            })
            for key in sorted(set(JIRA_KEY.findall(statement))):
                if key.startswith(("PI-", "CH")):
                    continue
                evidence.append({
                    "evidenceId": short_id("EVD"), "claimId": claim_id, "sourceType": "JIRA", "jiraKey": key,
                    "sourceTitle": key, "sourceURL": "", "sourceDate": "", "sourceVersion": "",
                    "evidenceStrength": "DIRECT", "evidenceStatus": "PROPOSED",
                    "excerpt": statement[:1000], "sourceImportId": record["importId"],
                })
            for url in URL_RE.findall(statement):
                evidence.append({
                    "evidenceId": short_id("EVD"), "claimId": claim_id,
                    "sourceType": "CONFLUENCE" if "confluence" in url.lower() or "/wiki/" in url else "OTHER",
                    "jiraKey": "", "sourceTitle": url[:200], "sourceURL": url[:1000], "sourceDate": "",
                    "sourceVersion": "", "evidenceStrength": "DIRECT", "evidenceStatus": "PROPOSED",
                    "excerpt": statement[:1000], "sourceImportId": record["importId"],
                })
        divisions.discard("")
        blocks[-1]["division"] = "BOTH" if divisions == {"PC", "VAN"} or "BOTH" in divisions else (divisions.pop() if len(divisions) == 1 else "")
    return {"knowledgeBlocks": blocks, "claims": claims, "evidence": evidence}
