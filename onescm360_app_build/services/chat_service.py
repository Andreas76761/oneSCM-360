"""Internal chat bot: route a question to one tool call, then run it on local data.

The design follows FunctionGemma (google/functiongemma-270m-it): a small router
turns natural language into exactly one function call with structured
arguments; the application executes the function. The router is either
rule-based (default, offline, deterministic) or an optional local model on
localhost (e.g. FunctionGemma served by Ollama). All tools are read-only.
External systems (Jira, Confluence, Rovo, web) are recognised but not
connected: there is no Graph/Entra integration and no token in this app.
"""
from __future__ import annotations

import http.client
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from .claim_service import evidence_factor, find_roles, object_tokens
from .storage import LOCK, now_iso

MAX_MESSAGE = 2000
DIMENSIONS = ["questions", "evidence", "roles", "division", "pi", "confidence"]
EXTERNAL_SYSTEMS = ["jira", "confluence", "rovo", "web"]

TOOLS = [
    {"name": "search_knowledge", "description": "Search the internal oneSCM knowledge (claims and knowledge blocks) for a topic or question.",
     "parameters": {"type": "object", "properties": {
         "query": {"type": "string", "description": "search terms"},
         "chapter": {"type": "string", "description": "chapter id such as CH01"},
         "role": {"type": "string", "description": "role id such as Dealer or MO"},
         "domain": {"type": "string", "description": "domain id such as finance-management"}}, "required": ["query"]}},
    {"name": "get_coverage", "description": "Get readiness, gate and coverage dimensions of a chapter.",
     "parameters": {"type": "object", "properties": {
         "chapter": {"type": "string", "description": "chapter id such as CH01"},
         "dimension": {"type": "string", "enum": DIMENSIONS, "description": "single coverage dimension"}}, "required": ["chapter"]}},
    {"name": "list_blockers", "description": "List the hard blockers that keep a chapter gate BLOCKED.",
     "parameters": {"type": "object", "properties": {"chapter": {"type": "string", "description": "chapter id"}}, "required": ["chapter"]}},
    {"name": "list_conflicts", "description": "List detected conflicts between claims.",
     "parameters": {"type": "object", "properties": {
         "chapter": {"type": "string", "description": "chapter id"},
         "status": {"type": "string", "enum": ["OPEN", "RESOLVED", "ACCEPTED"], "description": "conflict status"}}, "required": []}},
    {"name": "find_claims", "description": "List claims filtered by chapter, review status, evidence state, role or criticality.",
     "parameters": {"type": "object", "properties": {
         "chapter": {"type": "string", "description": "chapter id"},
         "validation_status": {"type": "string", "enum": ["DRAFT", "REVIEWED", "CONFIRMED", "REJECTED"], "description": "review status"},
         "evidence": {"type": "string", "enum": ["missing", "indirect", "direct"], "description": "evidence strength"},
         "role": {"type": "string", "description": "role id"},
         "criticality": {"type": "string", "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW"], "description": "criticality"}}, "required": []}},
    {"name": "get_claim", "description": "Show one claim with its evidence.",
     "parameters": {"type": "object", "properties": {"claim_id": {"type": "string", "description": "claim id such as CLM-1A2B3C4D"}}, "required": ["claim_id"]}},
    {"name": "lookup_rule", "description": "Look up a term in the rule set: abbreviation, explanation, synonym, naming convention or system.",
     "parameters": {"type": "object", "properties": {"term": {"type": "string", "description": "term or abbreviation"}}, "required": ["term"]}},
    {"name": "list_imports", "description": "List imported files filtered by chapter, language, role or domain.",
     "parameters": {"type": "object", "properties": {
         "chapter": {"type": "string", "description": "chapter id"},
         "language": {"type": "string", "enum": ["DE", "EN", "DE+EN"], "description": "language"},
         "role": {"type": "string", "description": "role id"},
         "domain": {"type": "string", "description": "domain id"}}, "required": []}},
    {"name": "search_tables", "description": "Search the extracted tables by content or chapter.",
     "parameters": {"type": "object", "properties": {
         "query": {"type": "string", "description": "search terms"},
         "chapter": {"type": "string", "description": "chapter id"}}, "required": []}},
    {"name": "search_external", "description": "Search an external system (Jira, Confluence, Rovo or the public web). Not connected in this app.",
     "parameters": {"type": "object", "properties": {
         "system": {"type": "string", "enum": EXTERNAL_SYSTEMS, "description": "external system"},
         "query": {"type": "string", "description": "search query"}}, "required": ["system", "query"]}},
]
TOOL_LABELS_DE = {
    "search_knowledge": "Internes Wissen (Claims, Knowledge Blocks) durchsuchen",
    "get_coverage": "Readiness, Gate und Coverage eines Kapitels",
    "list_blockers": "Hard Blocker eines Kapitels",
    "list_conflicts": "Erkannte Konflikte zwischen Claims",
    "find_claims": "Claims nach Kapitel, Status, Evidence, Rolle, Kritikalität filtern",
    "get_claim": "Einen Claim mit Evidence anzeigen",
    "lookup_rule": "Begriff im Regelwerk nachschlagen",
    "list_imports": "Importe nach Kapitel, Sprache, Rolle, Domäne",
    "search_tables": "Extrahierte Tabellen durchsuchen",
    "search_external": "Jira, Confluence, Rovo, Web – erkannt, aber nicht angebunden",
}
TOOL_NAMES = [t["name"] for t in TOOLS]
TOOL_BY_NAME = {t["name"]: t for t in TOOLS}

QUESTION_WORDS = re.compile(r"\b(was|wie|wer|wo|wann|welche[rsmn]?|warum|wieso|gibt es|zeige?|zeig mir|liste|nenne|finde|suche|"
                            r"what|how|who|where|when|which|why|show|list|find|search|bitte|mir|uns|im|in|zu|zum|zur|für|for|about|über|"
                            r"ist|sind|gilt|gelten|sagt|der|die|das|den|dem|des|ein|eine|einen|the|a|an|is|are|does|do)\b", re.I)
CHAPTER_RE = re.compile(r"\b(?:CH\s*0?(\d{1,2})|Kapitel\s*0?(\d{1,2})|Chapter\s*0?(\d{1,2}))\b", re.I)
CLAIM_RE = re.compile(r"\bCLM-[A-Z0-9]{4,12}\b", re.I)
JIRA_KEY_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,9}-\d{1,6}\b")


class ChatError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------------------------- routing
def _chapter(text: str) -> str:
    match = CHAPTER_RE.search(text)
    if not match:
        return ""
    number = int(next(g for g in match.groups() if g))
    return f"CH{number:02d}" if 1 <= number <= 16 else ""


def _clean_query(text: str) -> str:
    text = CHAPTER_RE.sub(" ", text)
    text = re.sub(r"[?!.,;:\"„“'()]", " ", text)
    words = [w for w in text.split() if not QUESTION_WORDS.fullmatch(w)]
    return " ".join(words).strip()[:300] or text.strip()[:300]


def _term(text: str) -> str:
    quoted = re.search(r"[\"„“']([^\"„“']{1,60})[\"„“']", text)
    if quoted:
        return quoted.group(1).strip()
    match = re.search(r"(?:bedeutet|bedeuten|heißt|heisst|steht|meint|means|stand for|stands for|abkürzung|abbreviation|"
                      r"erklärung|definition|synonym|schreibweise|regel)\s+(?:für\s+|von\s+|of\s+|for\s+|zu\s+)?(.+)", text, re.I)
    candidate = match.group(1) if match else text
    if match and re.fullmatch(r"\s*(?:die\s+|das\s+|der\s+)?(abkürzung|abbreviation)?\s*", candidate or "", re.I):
        candidate = text
    words = [w for w in re.findall(r"[\wÄÖÜäöüß+-]+", candidate) if not QUESTION_WORDS.fullmatch(w)
             and w.lower() not in {"bedeutet", "heißt", "heisst", "steht", "abkürzung", "abbreviation", "erklärung", "definition", "synonym", "schreibweise", "regel", "means", "mean"}]
    filler = {"man", "richtig", "korrekt", "schreibt", "schreiben", "geschrieben", "spell", "spelled", "correctly"}
    words = [w for w in words if w.lower() not in filler]
    if not words and match:
        # The term stands before the keyword ("Wie schreibt man onescm richtig? Schreibweise bitte").
        return _term(text[:match.start()] + " ") if text[:match.start()].strip() else ""
    upper = [w for w in words if w.isupper() and len(w) >= 2]
    return (upper[0] if upper else " ".join(words[:3])).strip()


def rule_route(message: str, roles=(), domains=()) -> dict:
    """Deterministic router: returns {"tool": name, "arguments": {...}} (tool may be "none")."""
    text = message.strip()
    low = text.lower()
    chapter = _chapter(text)
    role_hits = find_roles(text, roles)
    role = role_hits[0][1] if role_hits else ""
    domain = ""
    for d in domains:
        if d["name"].lower() in low or any(len(k) > 5 and re.search(r"(?<!\w)" + re.escape(k) + r"(?!\w)", low) for k in d.get("keywords", [])):
            domain = d["id"]
            break

    def with_filters(args, keys):
        values = {"chapter": chapter, "role": role, "domain": domain}
        args.update({k: values[k] for k in keys if values.get(k)})
        return args

    if re.fullmatch(r"\s*(hallo|hi|hey|servus|moin|guten (tag|morgen|abend)|hilfe|help|was kannst du\??|wie funktionierst du\??)[\s!.?]*", low):
        return {"tool": "none", "arguments": {}}
    claim = CLAIM_RE.search(text)
    if claim:
        return {"tool": "get_claim", "arguments": {"claim_id": claim.group(0).upper()}}

    only_rovo = re.search(r"\b(nur|ausschließlich|only)\s+(auf\s+|aus\s+|von\s+|on\s+|from\s+)?rovo\b", low)
    external = None
    if only_rovo and re.search(r"\b(claims?|aussagen?|evidence|nachweis\w*)\b", low):
        external = None
    elif re.search(r"\bjira\b", low) or (JIRA_KEY_RE.search(text) and not chapter):
        external = "jira"
    elif re.search(r"\bconfluence\b", low):
        external = "confluence"
    elif re.search(r"\brovo\b", low):
        external = "rovo"
    elif re.search(r"\b(google|internet|im web|web search|websuche|öffentlich|public|aktienkurs|stock price|wetter|weather|news|nachrichten)\b", low):
        external = "web"
    if external:
        query = _clean_query(re.sub(r"\b(jira|confluence|rovo|google|internet|web)\b", " ", text, flags=re.I)) or text
        key = JIRA_KEY_RE.search(text)
        return {"tool": "search_external", "arguments": {"system": external, "query": key.group(0) if key and external == "jira" else query}}

    if re.search(r"\b(blocker|blockiert|blocked|hard gate|warum.*gate|why.*gate)\b", low):
        return {"tool": "list_blockers", "arguments": {"chapter": chapter or "CH01"}}
    if re.search(r"\b(konflikt\w*|widerspr\w*|conflict\w*|contradict\w*)\b", low):
        args = with_filters({}, ["chapter"])
        if re.search(r"\b(offen\w*|open)\b", low):
            args["status"] = "OPEN"
        elif re.search(r"\b(gelöst|resolved)\b", low):
            args["status"] = "RESOLVED"
        return {"tool": "list_conflicts", "arguments": args}
    if re.search(r"\b(coverage|abdeckung|abgedeckt|readiness|reifegrad des kapitels|gate|wie weit|fortschritt|progress|"
                 r"wie steht|stand (von|des|bei)|status (von|des) (kapitel|ch))\b", low) or (chapter and re.search(r"\bsteht\b.*\bda\b", low)):
        args = {"chapter": chapter or "CH01"}
        for dim, pattern in [("evidence", r"evidence|nachweis"), ("roles", r"rollen|roles"), ("division", r"pc/van|division|pc und van"),
                             ("pi", r"\bpi\b|release"), ("confidence", r"confidence|vertrauen"), ("questions", r"fragen|questions")]:
            if re.search(pattern, low):
                args["dimension"] = dim
                break
        return {"tool": "get_coverage", "arguments": args}
    if re.search(r"\b(abkürzung|abbreviation|bedeutet|bedeuten|heißt|heisst|steht für|wofür steht|wofür stehen|stands? for|means|"
                 r"erklärung|definition|synonym|schreibweise|regelwerk|regel für)\b", low):
        return {"tool": "lookup_rule", "arguments": {"term": _term(text)}}
    if re.search(r"\b(import\w*|datei\w*|hochgeladen|uploads?|files?)\b", low):
        args = with_filters({}, ["chapter", "role", "domain"])
        for lang in ("DE+EN", "DE", "EN"):
            if re.search(r"(?<![\w+])" + re.escape(lang) + r"(?![\w+])", text):
                args["language"] = lang
                break
        if re.search(r"\b(englisch\w*|english)\b", low):
            args["language"] = "EN"
        elif re.search(r"\b(deutsch\w*|german)\b", low):
            args["language"] = "DE"
        return {"tool": "list_imports", "arguments": args}
    if re.search(r"\b(tabelle\w*|table\w*|matrix)\b", low):
        query = _clean_query(re.sub(r"\b(tabelle\w*|table\w*)\b", " ", text, flags=re.I))
        return {"tool": "search_tables", "arguments": with_filters({"query": query} if query else {}, ["chapter"])}
    claims_words = re.search(r"\b(claims?|aussagen?)\b", low)
    filters = {}
    if re.search(r"\b(ohne (evidence|nachweis)|kein\w* (evidence|nachweis\w*|beleg\w*)|unbelegt\w*|fehlende\w* (evidence|nachweis\w*)|"
                 r"nicht belegt|missing evidence|without evidence|no evidence)\b", low):
        filters["evidence"] = "missing"
    elif re.search(r"\b(indirekt\w*|indirect)\b", low) or only_rovo:
        filters["evidence"] = "indirect"
    if re.search(r"\b(ungeprüft\w*|offen\w*|draft|entwurf|nicht geprüft|unreviewed)\b", low):
        filters["validation_status"] = "DRAFT"
    elif re.search(r"\b(bestätigt\w*|confirmed|freigegeben\w*)\b", low):
        filters["validation_status"] = "CONFIRMED"
    elif re.search(r"\b(abgelehnt\w*|rejected)\b", low):
        filters["validation_status"] = "REJECTED"
    if re.search(r"\b(kritisch\w*|critical)\b", low):
        filters["criticality"] = "CRITICAL"
    if claims_words or filters:
        return {"tool": "find_claims", "arguments": with_filters(filters, ["chapter", "role"])}
    query = _clean_query(text)
    if len(query) < 2:
        return {"tool": "none", "arguments": {}}
    return {"tool": "search_knowledge", "arguments": with_filters({"query": query}, ["chapter", "role", "domain"])}


def validate_call(tool: str, arguments, roles=(), domains=()) -> dict:
    """Keep only declared arguments with valid values; raise if the call is unusable."""
    if tool not in TOOL_BY_NAME:
        raise ChatError(f"Unbekanntes Werkzeug „{tool}“.")
    if not isinstance(arguments, dict):
        arguments = {}
    spec = TOOL_BY_NAME[tool]["parameters"]
    clean = {}
    for key, schema in spec["properties"].items():
        value = arguments.get(key)
        if value in (None, ""):
            continue
        value = str(value).strip()[:300]
        if key == "chapter":
            value = _chapter(value) or (value.upper() if re.fullmatch(r"CH(0[1-9]|1[0-6])", value.upper()) else "")
        elif key == "role" and roles:
            hits = find_roles(value, roles)
            value = hits[0][1] if hits else next((r["id"] for r in roles if r["id"].casefold() == value.casefold()), "")
        elif key == "domain" and domains:
            value = next((d["id"] for d in domains if value.casefold() in (d["id"], d["name"].casefold())), "")
        elif "enum" in schema:
            value = next((e for e in schema["enum"] if e.casefold() == value.casefold()), "")
        if value:
            clean[key] = value
    missing = [k for k in spec.get("required", []) if k not in clean]
    if missing:
        raise ChatError(f"Pflichtparameter fehlt: {', '.join(missing)}.")
    return clean


# ---------------------------------------------------------------------- optional local model
FUNCTION_CALL_RE = re.compile(r"<start_function_call>\s*call:([A-Za-z_][\w]*)\{(.*?)\}\s*<end_function_call>", re.S)
ARG_RE = re.compile(r"([A-Za-z_][\w]*):(?:<escape>(.*?)<escape>|([^,}]*))", re.S)


def parse_model_output(message: dict) -> tuple[str, dict] | None:
    """Accept Ollama/OpenAI style tool_calls or the raw FunctionGemma call syntax."""
    calls = message.get("tool_calls") or []
    if calls:
        function = calls[0].get("function", {})
        arguments = function.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except ValueError:
                arguments = {}
        return function.get("name", ""), arguments if isinstance(arguments, dict) else {}
    match = FUNCTION_CALL_RE.search(message.get("content") or "")
    if match:
        args = {m.group(1): (m.group(2) if m.group(2) is not None else m.group(3)).strip() for m in ARG_RE.finditer(match.group(2))}
        return match.group(1), args
    return None


class LocalModelRouter:
    """Calls a model on localhost via the Ollama /api/chat API with tool declarations."""

    def __init__(self, url: str, model: str, timeout: float = 30):
        self.url = (url or "").strip() or "http://127.0.0.1:11434"
        self.model = (model or "").strip() or "functiongemma"
        self.timeout = timeout
        parsed = urlparse(self.url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.username or parsed.query:
            raise ChatError("Das lokale Modell muss über http://127.0.0.1 oder http://localhost erreichbar sein.")
        self.host, self.port, self.base = parsed.hostname, parsed.port or 11434, parsed.path.rstrip("/")

    def route(self, message: str) -> tuple[str, dict]:
        body = {"model": self.model, "stream": False, "options": {"temperature": 0},
                "messages": [{"role": "system", "content": "You are a model that can do function calling with the following functions"},
                             {"role": "user", "content": message}],
                "tools": [{"type": "function", "function": t} for t in TOOLS]}
        connection = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        try:
            connection.request("POST", f"{self.base}/api/chat", json.dumps(body).encode(), {"Content-Type": "application/json"})
            response = connection.getresponse()
            raw = response.read(1_000_001)
        except (OSError, http.client.HTTPException) as exc:
            raise ChatError(f"Lokales Modell nicht erreichbar ({self.url}).", 502) from exc
        finally:
            connection.close()
        if response.status != 200 or len(raw) > 1_000_000:
            raise ChatError(f"Lokales Modell meldet HTTP {response.status} (Modell „{self.model}“ installiert?).", 502)
        try:
            envelope = json.loads(raw)
        except ValueError as exc:
            raise ChatError("Lokales Modell lieferte kein JSON.", 502) from exc
        result = parse_model_output(envelope.get("message") or {})
        if not result:
            raise ChatError("Das Modell hat keinen Werkzeugaufruf erzeugt.", 502)
        return result


# --------------------------------------------------------------------------------- the service
class ChatService:
    def __init__(self, data_dir, knowledge, imports, rules, classification, compute_coverage, chapters, eval_path: Path,
                 router_url: str = "", router_model: str = ""):
        self.data = data_dir
        self.knowledge = knowledge
        self.imports = imports
        self.rules = rules
        self.classification = classification
        self.compute_coverage = compute_coverage
        self.chapters = chapters
        self.eval_path = Path(eval_path)
        self.router_url = router_url
        self.router_model = router_model

    @property
    def feedback_path(self) -> Path:
        return self.data.root / "chat_feedback.jsonl"

    def _domains(self):
        return self.classification.config()["domains"]

    def _roles(self):
        return self.classification.role_catalog()

    def info(self) -> dict:
        return {"tools": [{**t, "label": TOOL_LABELS_DE[t["name"]]} for t in TOOLS], "router": {"modes": ["rules", "model"], "url": self.router_url or "http://127.0.0.1:11434",
                                          "model": self.router_model or "functiongemma"}}

    # -- routing ---------------------------------------------------------------------
    def route(self, message: str, mode: str = "rules") -> dict:
        message = (message or "").strip()
        if not message:
            raise ChatError("Bitte eine Frage eingeben.")
        if len(message) > MAX_MESSAGE:
            raise ChatError(f"Die Frage ist länger als {MAX_MESSAGE} Zeichen.")
        if mode not in ("rules", "model"):
            raise ChatError("Router-Modus muss „rules“ oder „model“ sein.")
        notes = []
        router = "rules"
        if mode == "model":
            try:
                name, args = LocalModelRouter(self.router_url, self.router_model).route(message)
                call = {"tool": name, "arguments": validate_call(name, args, self._roles(), self._domains())}
                router = "model"
            except ChatError as exc:
                notes.append(f"{exc} Es wurde der Regel-Router verwendet.")
                call = rule_route(message, self._roles(), self._domains())
        else:
            call = rule_route(message, self._roles(), self._domains())
        if call["tool"] != "none":
            call["arguments"] = validate_call(call["tool"], call["arguments"], self._roles(), self._domains())
        return {**call, "router": router, "notes": notes}

    def ask(self, message: str, mode: str = "rules") -> dict:
        call = self.route(message, mode)
        result = self.execute(call["tool"], call["arguments"])
        return {"message": message.strip(), "call": {"tool": call["tool"], "arguments": call["arguments"]},
                "router": call["router"], "notes": call["notes"], **result, "answeredAt": now_iso()}

    # -- tools -------------------------------------------------------------------------
    def execute(self, tool: str, args: dict) -> dict:
        handler = getattr(self, f"_tool_{tool}", None)
        if handler is None:
            return self._tool_none(args)
        return handler(args)

    def _tool_none(self, _args):
        return {"title": "Keine passende Funktion erkannt", "text": "Ich kann Fragen zum internen Wissensbestand beantworten, z. B.:",
                "items": [{"label": e} for e in ("Was gilt für Stornierungen beim Dealer?", "Wie ist die Coverage von CH01?",
                                                  "Warum ist CH01 blockiert?", "Zeige unbelegte kritische Claims in CH01",
                                                  "Was bedeutet PI?", "Welche Konflikte sind offen?")]}

    def _claim_index(self):
        data = self.knowledge.load()
        blocks = {k["knowledgeId"]: k for k in data["knowledgeBlocks"]}
        factors = {}
        for ev in data["evidence"]:
            factors[ev["claimId"]] = max(factors.get(ev["claimId"], 0.0), evidence_factor(ev))
        return data, blocks, factors

    @staticmethod
    def _claim_item(claim, factor, score=None):
        return {"type": "claim", "id": claim["claimId"], "chapterId": claim["chapterId"], "questionId": claim["questionId"],
                "label": claim["canonicalStatement"], "role": claim.get("role", ""),
                "status": claim["validationStatus"], "criticality": claim["criticality"],
                "evidence": round(factor, 2), **({"score": round(score, 2)} if score is not None else {})}

    def _tool_search_knowledge(self, args):
        data, blocks, factors = self._claim_index()
        normalized, _ = self.rules.apply(args["query"])
        query = object_tokens(normalized) | object_tokens(args["query"])
        if not query:
            return {"title": "Suche", "text": "Die Suchanfrage enthält keine verwertbaren Begriffe.", "items": []}
        hits = []
        for claim in data["claims"]:
            if claim["validationStatus"] == "REJECTED":
                continue
            block = blocks.get(claim["knowledgeId"], {})
            if args.get("chapter") and claim["chapterId"] != args["chapter"]:
                continue
            if args.get("role") and claim.get("role") not in (args["role"], ""):
                continue
            if args.get("domain") and block.get("domain") != args["domain"]:
                continue
            tokens = object_tokens(claim["canonicalStatement"]) | object_tokens(block.get("topic", ""))
            overlap = len(query & tokens)
            if not overlap:
                continue
            score = overlap / len(query) + (0.2 if claim["validationStatus"] == "CONFIRMED" else 0) + 0.1 * factors.get(claim["claimId"], 0)
            hits.append((score, claim))
        hits.sort(key=lambda h: -h[0])
        items = [self._claim_item(c, factors.get(c["claimId"], 0.0), s) for s, c in hits[:8]]
        if not items:
            return {"title": "Keine Treffer im internen Wissen",
                    "text": "Zu dieser Frage gibt es noch keine Aussagen im Wissensbestand. Quelle in Rovo, Jira oder Confluence prüfen und importieren.",
                    "items": [], "suggestion": {"tool": "search_external", "arguments": {"system": "rovo", "query": args["query"]}}}
        confirmed = sum(1 for i in items if i["status"] == "CONFIRMED")
        text = f"{len(hits)} passende Aussage(n), die besten {len(items)} stehen unten."
        if confirmed < len(items):
            text += f" {len(items) - confirmed} davon sind noch nicht bestätigt (DRAFT/REVIEWED) – bitte nicht als gesicherte Auskunft verwenden."
        return {"title": f"Internes Wissen zu „{args['query']}“", "text": text, "items": items}

    def _tool_get_coverage(self, args):
        chapter = self.chapters.get(args["chapter"])
        cov = self.compute_coverage(args["chapter"])
        names = {"questions": "Questions", "evidence": "Evidence", "roles": "Roles", "division": "PC/VAN", "pi": "PI", "confidence": "Confidence"}
        keys = {"questions": "questionCoverage", "evidence": "evidenceCoverage", "roles": "roleCoverage",
                "division": "divisionCoverage", "pi": "piCoverage", "confidence": "confidence"}
        dims = [args["dimension"]] if args.get("dimension") else DIMENSIONS
        items = [{"type": "metric", "label": names[d], "value": cov[keys[d]]} for d in dims]
        text = f"Gate {cov['gate']} · Readiness {cov['readiness']:.1f} %. {cov['gateReason']}"
        return {"title": f"Coverage {chapter['chapterId']} – {chapter['title']}", "text": text, "items": items,
                "gate": cov["gate"], "link": {"tab": "coverage", "chapterId": chapter["chapterId"]}}

    def _tool_list_blockers(self, args):
        cov = self.compute_coverage(args["chapter"])
        items = [{"type": "text", "label": b, "id": (CLAIM_RE.search(b).group(0) if CLAIM_RE.search(b) else "")} for b in cov["blockers"]]
        text = (f"{args['chapter']} hat {len(items)} Hard Blocker – das Gate bleibt BLOCKED, egal wie hoch die Readiness ist."
                if items else f"{args['chapter']} hat keine Hard Blocker (Gate {cov['gate']}).")
        return {"title": f"Hard Blocker {args['chapter']}", "text": text, "items": items, "gate": cov["gate"],
                "link": {"tab": "coverage", "chapterId": args["chapter"]}}

    def _tool_list_conflicts(self, args):
        if args.get("chapter"):
            self.compute_coverage(args["chapter"])  # refresh detection
        conflicts = [c for c in self.knowledge.conflicts(args.get("chapter"))
                     if not args.get("status") or c["status"] == args["status"]]
        items = [{"type": "conflict", "id": c["conflictId"], "chapterId": c["chapterId"], "label": c["description"],
                  "status": c["status"], "criticality": c["severity"], "kind": c["type"]} for c in conflicts[:20]]
        scope = args.get("chapter") or "alle Kapitel"
        return {"title": f"Konflikte ({scope})", "text": f"{len(conflicts)} Konflikt(e) gefunden." if conflicts else "Keine Konflikte gefunden.",
                "items": items}

    def _tool_find_claims(self, args):
        data, _blocks, factors = self._claim_index()
        result = []
        for claim in data["claims"]:
            factor = factors.get(claim["claimId"], 0.0)
            if args.get("chapter") and claim["chapterId"] != args["chapter"]:
                continue
            if args.get("validation_status") and claim["validationStatus"] != args["validation_status"]:
                continue
            if not args.get("validation_status") and claim["validationStatus"] == "REJECTED":
                continue
            if args.get("role") and claim.get("role") != args["role"]:
                continue
            if args.get("criticality") and claim["criticality"] != args["criticality"]:
                continue
            evidence = args.get("evidence")
            if evidence == "missing" and factor >= 0.9:
                continue  # "missing" = no direct evidence
            if evidence == "indirect" and not 0 < factor < 0.9:
                continue
            if evidence == "direct" and factor < 0.9:
                continue
            result.append(self._claim_item(claim, factor))
        labels = {"missing": "ohne direkte Evidence", "indirect": "nur mit indirekter Evidence", "direct": "mit direkter Evidence"}
        parts = [args.get("chapter", ""), args.get("validation_status", ""), args.get("criticality", ""), args.get("role", ""),
                 labels.get(args.get("evidence", ""), "")]
        return {"title": "Claims " + " · ".join(p for p in parts if p), "text": f"{len(result)} Claim(s).", "items": result[:30]}

    def _tool_get_claim(self, args):
        claim = next((c for c in self.knowledge.claims() if c["claimId"].upper() == args["claim_id"].upper()), None)
        if not claim:
            return {"title": f"Claim {args['claim_id']}", "text": "Dieser Claim existiert nicht.", "items": []}
        evidence = self.knowledge.evidence(claim_id=claim["claimId"])
        items = [{"type": "evidence", "id": e["evidenceId"], "label": f"{e['sourceType']} · {e.get('jiraKey') or e.get('sourceTitle') or e.get('sourceURL')}",
                  "status": e["evidenceStatus"], "criticality": e["evidenceStrength"], "evidence": e["factor"]} for e in evidence]
        text = (f"„{claim['canonicalStatement']}“ – {claim['chapterId']} {claim['questionId']}, {claim['criticality']}, "
                f"Status {claim['validationStatus']}, Evidence-Faktor {claim['evidenceFactor']:.2f}.")
        return {"title": f"Claim {claim['claimId']}", "text": text, "items": items,
                "link": {"tab": "claims", "chapterId": claim["chapterId"], "claimId": claim["claimId"]}}

    def _tool_lookup_rule(self, args):
        term = args["term"].casefold()
        rules = self.rules.list()
        exact = [r for r in rules if r["source"].casefold() == term or r["target"].casefold() == term]
        partial = [r for r in rules if r not in exact and (term in r["source"].casefold() or (r["target"] and term in r["target"].casefold()))]
        labels = {"naming": "Namenskonvention", "system": "System", "synonym": "Synonym", "explanation": "Erklärung", "abbreviation": "Abkürzung"}
        items = [{"type": "rule", "id": r["id"], "label": f"{labels[r['category']]}: {r['source']}" + (f" → {r['target']}" if r["target"] else ""),
                  "status": labels[r["category"]]} for r in exact + partial]
        if not items:
            return {"title": f"Regelwerk: „{args['term']}“", "text": "Kein Eintrag im Regelwerk. Im Register Regelwerk kann er angelegt werden.", "items": [],
                    "link": {"tab": "rules"}}
        first = exact[0] if exact else partial[0]
        answer = {"abbreviation": f"{first['source']} steht für {first['target']}.", "explanation": f"{first['source']}: {first['target']}.",
                  "synonym": f"„{first['source']}“ wird kanonisch als „{first['target']}“ geführt.",
                  "naming": f"Richtige Schreibweise: {first['target']} (nicht „{first['source']}“).",
                  "system": f"{first['source']} ist ein erlaubtes System."}[first["category"]]
        return {"title": f"Regelwerk: „{args['term']}“", "text": answer, "items": items, "link": {"tab": "rules"}}

    def _tool_list_imports(self, args):
        rows = [r for r in self.imports.list() if r["status"] != "INVALID_JSON"
                and all(not args.get(k) or r.get(field) == args[k] for k, field in
                        (("chapter", "chapterId"), ("language", "language"), ("role", "role"), ("domain", "domain")))]
        items = [{"type": "import", "id": r["importId"], "chapterId": r["chapterId"], "label": r["file"], "status": r["status"],
                  "criticality": r.get("gate", ""), "role": r.get("role", ""), "language": r.get("language", "")} for r in rows[:30]]
        return {"title": "Importe", "text": f"{len(rows)} Import(e).", "items": items, "link": {"tab": "dashboard"}}

    def _tool_search_tables(self, args):
        tables = self.imports.tables(args.get("chapter"))
        query = object_tokens(args.get("query", ""))
        hits = []
        for table in tables:
            cells = " ".join([" ".join(table.get("header") or [])] + [" ".join(r) for r in table["rows"]])
            if query and not (query & object_tokens(cells)):
                continue
            hits.append({"type": "table", "id": table["tableId"], "chapterId": table["chapterId"],
                         "label": " | ".join(table.get("header") or table["rows"][0])[:200],
                         "status": table.get("sourceQuestionId") or "ohne Frage"})
        return {"title": "Tabellen", "text": f"{len(hits)} Tabelle(n).", "items": hits[:20], "link": {"tab": "tables"}}

    def _tool_search_external(self, args):
        names = {"jira": "Jira", "confluence": "Confluence", "rovo": "Rovo", "web": "Websuche"}
        system = names[args["system"]]
        return {"title": f"{system} ist nicht angebunden",
                "text": (f"Die Frage betrifft {system}. Diese App hat bewusst keine Verbindung zu externen Systemen "
                         "(kein Entra-ID/Graph, keine Tokens). Die Suchanfrage unten kann dort manuell gestellt werden; "
                         "relevante Ergebnisse anschließend als HTML/DOCX importieren oder als Evidence am Claim erfassen."),
                "items": [{"type": "query", "label": args["query"]}], "external": True}

    # -- evaluation & training data -------------------------------------------------------
    def evaluate(self, mode: str = "rules") -> dict:
        cases = json.loads(self.eval_path.read_text(encoding="utf-8"))["cases"]
        results = []
        for case in cases:
            try:
                call = self.route(case["message"], mode)
            except ChatError as exc:
                call = {"tool": "error", "arguments": {}, "router": mode, "notes": [str(exc)]}
            expected = case.get("arguments", {})
            ok = call["tool"] == case["tool"] and all(str(call["arguments"].get(k, "")).casefold() == str(v).casefold() for k, v in expected.items())
            results.append({"message": case["message"], "expected": {"tool": case["tool"], "arguments": expected},
                            "actual": {"tool": call["tool"], "arguments": call["arguments"]}, "router": call["router"], "ok": ok})
        return {"mode": mode, "passed": sum(r["ok"] for r in results), "total": len(results), "results": results}

    def feedback(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ChatError("Ungültiges Feedback.")
        message = str(payload.get("message", "")).strip()[:MAX_MESSAGE]
        tool = str(payload.get("tool", ""))
        if not message:
            raise ChatError("Die Frage fehlt.")
        if tool not in TOOL_NAMES:
            raise ChatError("Bitte ein gültiges Werkzeug wählen.")
        arguments = payload.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise ChatError("Ungültige Parameter.")
        if tool != rule_route(message, self._roles(), self._domains())["tool"] and not arguments:
            # Corrected tool: derive arguments with the rule router where possible, else use the question as query.
            derived = rule_route(message, self._roles(), self._domains())["arguments"]
            props = TOOL_BY_NAME[tool]["parameters"]["properties"]
            arguments = {k: v for k, v in derived.items() if k in props}
            if "query" in props and "query" not in arguments:
                arguments["query"] = _clean_query(message)
        try:
            arguments = validate_call(tool, arguments, self._roles(), self._domains())
        except ChatError as exc:
            raise ChatError(f"{exc} Bitte die Parameter ergänzen.") from exc
        entry = {"user_content": message, "tool_name": tool, "tool_arguments": arguments,
                 "correct": bool(payload.get("correct", True)), "source": "feedback", "createdAt": now_iso()}
        with LOCK:
            self.feedback_path.parent.mkdir(parents=True, exist_ok=True)
            with self.feedback_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def _feedback_entries(self) -> list[dict]:
        if not self.feedback_path.exists():
            return []
        entries = []
        for line in self.feedback_path.read_text(encoding="utf-8").splitlines():
            try:
                entries.append(json.loads(line))
            except ValueError:
                continue
        return entries

    def seed_examples(self) -> list[dict]:
        """Template examples over chapters, roles and domains (synthetic, like model distillation)."""
        examples = []
        roles = self._roles()
        domains = self._domains()
        for chapter in self.chapters.list():
            cid = chapter["chapterId"]
            n = int(cid[2:])
            examples += [
                (f"Wie ist die Coverage von {cid}?", "get_coverage", {"chapter": cid}),
                (f"Wie weit ist Kapitel {n}?", "get_coverage", {"chapter": cid}),
                (f"Wie hoch ist die Evidence-Abdeckung in {cid}?", "get_coverage", {"chapter": cid, "dimension": "evidence"}),
                (f"Warum ist {cid} blockiert?", "list_blockers", {"chapter": cid}),
                (f"Welche offenen Konflikte gibt es in {cid}?", "list_conflicts", {"chapter": cid, "status": "OPEN"}),
                (f"Zeige unbelegte Claims in {cid}", "find_claims", {"chapter": cid, "evidence": "missing"}),
                (f"Welche Claims in {cid} sind noch ungeprüft?", "find_claims", {"chapter": cid, "validation_status": "DRAFT"}),
                (f"Welche Tabellen gibt es in {cid}?", "search_tables", {"chapter": cid}),
                (f"Welche Dateien wurden für {cid} importiert?", "list_imports", {"chapter": cid}),
            ]
        for role in roles:
            examples.append((f"Welche Claims betreffen die Rolle {role['name']}?", "find_claims", {"role": role["id"]}))
        for domain in domains:
            examples.append((f"Welche Importe gehören zu {domain['name']}?", "list_imports", {"domain": domain["id"]}))
        for rule in self.rules.list():
            if rule["category"] in ("abbreviation", "explanation"):
                examples.append((f"Was bedeutet {rule['source']}?", "lookup_rule", {"term": rule["source"]}))
        examples += [
            ("Was sagt Jira zur Stornierung von Serviceverträgen?", "search_external", {"system": "jira", "query": "Stornierung Serviceverträgen"}),
            ("Suche in Confluence nach dem Freigabeprozess für Templates", "search_external", {"system": "confluence", "query": "Freigabeprozess Templates"}),
            ("Frag Rovo nach den PI17 Änderungen", "search_external", {"system": "rovo", "query": "PI17 Änderungen"}),
            ("Wie ist der aktuelle Aktienkurs von Mercedes?", "search_external", {"system": "web", "query": "aktuelle Aktienkurs Mercedes"}),
            ("Was gilt für die Stornierung von Aufträgen durch den Dealer?", "search_knowledge", {"query": "Stornierung Aufträgen Dealer"}),
        ]
        return [{"user_content": u, "tool_name": t, "tool_arguments": a, "source": "template"} for u, t, a in examples]

    def training_data(self, fmt: str = "notebook") -> str:
        """JSONL in the FunctionGemma notebook format or as chat messages with tool_calls."""
        rows = self.seed_examples() + [e for e in self._feedback_entries() if e.get("correct", True)]
        eval_messages = {c["message"].casefold() for c in json.loads(self.eval_path.read_text(encoding="utf-8"))["cases"]}
        rows = [r for r in rows if r["user_content"].casefold() not in eval_messages]  # keep the test set separate
        lines = []
        for row in rows:
            if fmt == "messages":
                record = {"messages": [
                    {"role": "developer", "content": "You are a model that can do function calling with the following functions"},
                    {"role": "user", "content": row["user_content"]},
                    {"role": "assistant", "tool_calls": [{"type": "function", "function": {"name": row["tool_name"], "arguments": row["tool_arguments"]}}]}],
                    "tools": [{"type": "function", "function": t} for t in TOOLS]}
            else:
                record = {"user_content": row["user_content"], "tool_name": row["tool_name"],
                          "tool_arguments": json.dumps(row["tool_arguments"], ensure_ascii=False)}
            lines.append(json.dumps(record, ensure_ascii=False))
        return "\n".join(lines) + "\n"
