"""Internal chat bot: route a question to one registered tool, let the policy decide, run it.

Architecture (oneSCM360 target picture):
    UI → local AI router (rules or FunctionGemma on localhost) → security/policy engine
       → tool layer (tool_registry.json) → internal data
The router only proposes "what should be done"; PolicyService decides "may it be
done". Knowledge questions follow the local-first order of the policy and stop
with "Keine freigegebene Quelle gefunden." – there is never an internet fallback.
"""
from __future__ import annotations

import http.client
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from .claim_service import evidence_factor, find_roles, object_tokens
from .policy_service import STATUS_MAP, Decision, PolicyError
from .storage import LOCK, now_iso

MAX_MESSAGE = 2000
NO_SOURCE = "Keine freigegebene Quelle gefunden."
STATUS_LABEL = {v: k for k, v in STATUS_MAP.items()}

QUESTION_WORDS = re.compile(r"\b(was|wie|wer|wo|wann|welche[rsmn]?|warum|wieso|gibt es|zeige?|zeig mir|liste|nenne|finde|suche|such|"
                            r"what|how|who|where|when|which|why|show|list|find|search|bitte|mir|uns|im|in|zu|zum|zur|für|for|about|über|"
                            r"ist|sind|gilt|gelten|sagt|der|die|das|den|dem|des|ein|eine|einen|the|a|an|is|are|does|do|bei|beim|nach|"
                            r"dazu|darin|steht|stehen|wofür|woran|worüber|bedeutet|bedeuten|heißt|heisst|meint|eigentlich|gerade|aktuell)\b", re.I)
CHAPTER_RE = re.compile(r"\b(?:CH\s*0?(\d{1,2})|Kapitel\s*0?(\d{1,2})|Chapter\s*0?(\d{1,2}))\b", re.I)
CLAIM_RE = re.compile(r"\bCLM-[A-Z0-9]{4,12}\b", re.I)
QUESTION_ID_RE = re.compile(r"\b(\d{2})-F(\d{2})\b", re.I)
JIRA_KEY_RE = re.compile(r"\b(?!CLM-|CH\d)[A-Z][A-Z0-9]{1,9}-\d{1,6}\b")


class ChatError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------------------------- rule router
def _chapter(text: str) -> str:
    match = CHAPTER_RE.search(text)
    if match:
        number = int(next(g for g in match.groups() if g))
        return f"CH{number:02d}" if 1 <= number <= 16 else ""
    qid = QUESTION_ID_RE.search(text)
    return f"CH{qid.group(1)}" if qid and 1 <= int(qid.group(1)) <= 16 else ""


def _clean_query(text: str) -> str:
    text = CHAPTER_RE.sub(" ", text)
    text = re.sub(r"[?!.,;:\"„“'()]", " ", text)
    words = [w for w in text.split() if not QUESTION_WORDS.fullmatch(w)]
    return " ".join(words).strip()[:300] or text.strip()[:300]


def _vehicle(low: str) -> str:
    pc = re.search(r"\b(pc|pkw|passenger cars?)\b", low)
    van = re.search(r"\b(van|vans|transporter)\b", low)
    cv = re.search(r"\b(cv|commercial vehicles?|nutzfahrzeug\w*|lkw)\b", low)
    if sum(map(bool, (pc, van, cv))) > 1 or re.search(r"\b(alle (fahrzeug|division)\w*|all vehicles?)\b", low):
        return "ALL"
    return "PC" if pc else "VAN" if van else "CV" if cv else ""


def _status(low: str) -> str:
    if re.search(r"\b(freigegeben\w*|released|bestätigt\w*|confirmed)\b", low):
        return "Released"
    if re.search(r"\b(geprüft\w*|reviewed)\b", low) and not re.search(r"\b(un|nicht )geprüft", low):
        return "Reviewed"
    if re.search(r"\b(entwurf|entwürfe|draft|ungeprüft\w*|nicht geprüft|offen\w*)\b", low):
        return "Draft"
    if re.search(r"\b(abgelehnt\w*|rejected)\b", low):
        return "Rejected"
    return ""


def _language(text: str, low: str) -> str:
    if re.search(r"\b(englisch\w*|english|auf en)\b", low) or re.search(r"(?<![\w+])EN(?![\w+])", text):
        return "EN"
    if re.search(r"\b(deutsch\w*|german|auf de)\b", low) or re.search(r"(?<![\w+])DE(?![\w+])", text):
        return "DE"
    return ""


def rule_route(message: str, roles=()) -> dict:
    """Deterministic router: {"tool": name, "arguments": {...}}. Unregistered tool names are left to the policy (DENY)."""
    text = message.strip()
    low = text.lower()
    chapter = _chapter(text)
    hits = find_roles(text, roles)
    role = hits[0][1] if hits else ""
    vehicle = _vehicle(low)

    def put(args, **values):
        args.update({k: v for k, v in values.items() if v})
        return args

    if re.fullmatch(r"\s*(hallo|hi|hey|servus|moin|guten (tag|morgen|abend)|hilfe|help|was kannst du\??|wie funktionierst du\??)[\s!.?]*", low):
        return {"tool": "none", "arguments": {}}

    # Requests the registry deliberately does not offer – proposed, then denied by the policy (audited).
    if re.search(r"\b(google|internet|im web|websuche|web search|öffentlich\w* (quelle|suche)|aktienkurs|stock price|wetter|weather|chatgpt|openai|hugging ?face)\b", low):
        return {"tool": "search_web", "arguments": {"query": _clean_query(text)}}
    if re.search(r"\b(e-?mail|mail an|sende|schick\w*|send)\b", low) and re.search(r"\b(an|to)\b|@", low):
        return {"tool": "send_email", "arguments": {}}
    if re.search(r"\b(lösch\w*|delete|entfern\w*|drop)\b", low):
        return {"tool": "delete_data", "arguments": {}}
    if re.search(r"\b(hochladen nach|upload to|teile? öffentlich|public share|freigeben für extern)\b", low):
        return {"tool": "upload_external", "arguments": {}}

    claim = CLAIM_RE.search(text)
    if re.search(r"\b(export\w*|paket|package|csv|json-datei|review-paket)\b", low):
        fmt = "csv" if "csv" in low else "json" if re.search(r"\bjson\b", low) else "review_package"
        return {"tool": "export_knowledge", "arguments": put({"chapter": chapter or "CH01"}, format=fmt)}
    if re.search(r"\b(evidence|nachweis\w*|beleg\w*)\b", low) and (claim or re.search(r"\b(welche|zeige|liste|alle|hole|quellen)\b", low)) \
            and not re.search(r"\b(ohne|kein\w*|fehlend\w*|unbelegt\w*|nur)\b", low) \
            and not re.search(r"\b(coverage|abdeckung|readiness)\b", low):
        source = next((s for s, p in (("JIRA", r"jira"), ("CONFLUENCE", r"confluence"), ("ROVO", r"rovo")) if re.search(p, low)), "")
        return {"tool": "get_evidence", "arguments": put({}, claim_id=claim.group(0).upper() if claim else "", chapter=chapter, source_type=source)}
    if claim:
        return {"tool": "get_claims", "arguments": {"claim_id": claim.group(0).upper()}}

    only_rovo = re.search(r"\b(nur|ausschließlich|only)\s+(auf\s+|aus\s+|von\s+|on\s+|from\s+)?rovo\b", low)
    key = JIRA_KEY_RE.search(text)
    if not only_rovo:
        if re.search(r"\bjira\b", low) or (key and not chapter):
            query = _clean_query(re.sub(r"\bjira\b", " ", text, flags=re.I))
            return {"tool": "search_jira", "arguments": put({}, jira_key=key.group(0) if key else "", query="" if key else query, chapter=chapter)}
        if re.search(r"\bconfluence\b", low):
            return {"tool": "search_confluence", "arguments": put({"query": _clean_query(re.sub(r"\bconfluence\b", " ", text, flags=re.I))}, chapter=chapter)}
        if re.search(r"\brovo\b", low):
            return {"tool": "query_rovo", "arguments": put({"query": _clean_query(re.sub(r"\b(frag\w*|rovo)\b", " ", text, flags=re.I))}, chapter=chapter)}

    if re.search(r"\b(valid\w*|prüfe? (das |die )?kapitel|kapitel prüfen|konsisten\w*|blocker|blockiert|blocked|konflikt\w*|widerspr\w*|"
                 r"conflict\w*|fehler im kapitel|was fehlt)\b", low) and not re.search(r"\b(\w*relevanz|coverage|abdeckung|abgedeckt)\b", low):
        return {"tool": "validate_chapter", "arguments": {"chapter": chapter or "CH01"}}
    if re.search(r"\b(coverage|abdeckung|abgedeckt|readiness|gate|wie weit|fortschritt|progress|wie steht|stand (von|des|bei))\b", low) \
            or (chapter and re.search(r"\bsteht\b.*\bda\b", low)) or (chapter and re.search(r"\b(prüfe|check)\b.*\brelevanz\b", low)):
        dims = []
        for dim, pattern in [("questions", r"fragen|questions"), ("claims", r"claims|aussagen"), ("evidence", r"evidence|nachweis"),
                             ("roles", r"rollen|roles"), ("PC", r"\bpc\b|pkw"), ("VAN", r"\bvan\b|transporter"), ("CV", r"\bcv\b|nutzfahrzeug"),
                             ("PI_status", r"\bpi\b|release")]:
            if re.search(pattern, low):
                dims.append(dim)
        return {"tool": "calculate_coverage", "arguments": put({"chapter": chapter or "CH01"}, dimensions=dims)}

    claims_words = re.search(r"\b(claims?|aussagen?)\b", low)
    filters = {}
    if re.search(r"\b(ohne (evidence|nachweis)|kein\w* (evidence|nachweis\w*|beleg\w*)|unbelegt\w*|fehlende\w* (evidence|nachweis\w*)|"
                 r"nicht belegt|missing evidence|without evidence|no evidence)\b", low):
        filters["evidence"] = "missing"
    elif re.search(r"\b(indirekt\w*|indirect)\b", low) or only_rovo:
        filters["evidence"] = "indirect"
    if re.search(r"\b(kritisch\w*|critical)\b", low):
        filters["criticality"] = "CRITICAL"
    status = _status(low)
    if claims_words or filters:
        return {"tool": "get_claims", "arguments": put(filters, chapter=chapter, role=role, status=status,
                                                       vehicle_type=vehicle if vehicle != "ALL" else "")}

    question = QUESTION_ID_RE.search(text)
    if question or re.search(r"\b(handbuch\w*|manual|kapiteltext|antwort (auf|zu) frage)\b", low):
        query = _clean_query(re.sub(r"\b(handbuch\w*|manual)\b", " ", QUESTION_ID_RE.sub(" ", text), flags=re.I)) or "Handbuch"
        return {"tool": "search_manual", "arguments": put({"query": query}, chapter=chapter,
                                                          question=question.group(0).upper() if question else "", language=_language(text, low))}
    query = _clean_query(text)
    if len(query) < 2:
        return {"tool": "none", "arguments": {}}
    return {"tool": "search_knowledge", "arguments": put({"query": query}, chapter=chapter, vehicle_type=vehicle, status=status,
                                                         language=_language(text, low), role=role)}


# ---------------------------------------------------------------------- optional local model
FUNCTION_CALL_RE = re.compile(r"<start_function_call>\s*call:([A-Za-z_][\w]*)\{(.*?)\}\s*<end_function_call>", re.S)
ARG_RE = re.compile(r"([A-Za-z_][\w]*):(?:<escape>(.*?)<escape>|(\[[^\]]*\])|([^,}]*))", re.S)


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
        args = {}
        for m in ARG_RE.finditer(match.group(2)):
            if m.group(2) is not None:
                args[m.group(1)] = m.group(2).strip()
            elif m.group(3) is not None:
                args[m.group(1)] = [v.replace("<escape>", "").strip(" \"'") for v in m.group(3)[1:-1].split(",") if v.strip()]
            else:
                args[m.group(1)] = (m.group(4) or "").strip()
        return match.group(1), args
    return None


class LocalModelRouter:
    """Calls a model on localhost via the Ollama /api/chat API with the registry's function declarations."""

    def __init__(self, url: str, model: str, declarations: list[dict], timeout: float = 30):
        self.url = (url or "").strip() or "http://127.0.0.1:11434"
        self.model = (model or "").strip() or "functiongemma"
        self.declarations = declarations
        self.timeout = timeout
        parsed = urlparse(self.url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.username or parsed.query:
            raise ChatError("Das lokale Modell muss über http://127.0.0.1 oder http://localhost erreichbar sein (external_llm = false).")
        self.host, self.port, self.base = parsed.hostname, parsed.port or 11434, parsed.path.rstrip("/")

    def route(self, message: str) -> tuple[str, dict]:
        body = {"model": self.model, "stream": False, "options": {"temperature": 0},
                "messages": [{"role": "system", "content": "You are a model that can do function calling with the following functions"},
                             {"role": "user", "content": message}],
                "tools": [{"type": "function", "function": d} for d in self.declarations]}
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
    def __init__(self, data_dir, knowledge, imports, rules, classification, compute_coverage, chapters, policy,
                 export_chapter, eval_path: Path, router_url: str = "", router_model: str = ""):
        self.data = data_dir
        self.knowledge = knowledge
        self.imports = imports
        self.rules = rules
        self.classification = classification
        self.compute_coverage = compute_coverage
        self.chapters = chapters
        self.policy = policy
        self.export_chapter = export_chapter
        self.eval_path = Path(eval_path)
        self.router_url = router_url
        self.router_model = router_model

    @property
    def feedback_path(self) -> Path:
        return self.data.root / "chat_feedback.jsonl"

    def _roles(self):
        return self.classification.role_catalog()

    def info(self) -> dict:
        tools = [{"name": t["name"], "purpose": t["purpose"], "source": t["source_label"], "description": t["description"],
                  "writes": t["security"]["writes"], "classification": t["security"]["classification"],
                  "network": t["security"]["network"], "operation": t["security"]["allowed_operations"][0],
                  "confirmation": t["security"].get("confirmation_required", False),
                  "connector": (t.get("connector") or {}).get("configured", True)} for t in self.policy.tools()]
        return {"tools": tools, "policy": self.policy.summary(),
                "router": {"modes": ["rules", "model"], "url": self.router_url or "http://127.0.0.1:11434",
                           "model": self.router_model or "functiongemma"}}

    # -- routing -------------------------------------------------------------------------
    def route(self, message: str, mode: str = "rules") -> dict:
        message = (message or "").strip()
        if not message:
            raise ChatError("Bitte eine Frage eingeben.")
        if len(message) > MAX_MESSAGE:
            raise ChatError(f"Die Frage ist länger als {MAX_MESSAGE} Zeichen.")
        if mode not in ("rules", "model"):
            raise ChatError("Router-Modus muss „rules“ oder „model“ sein.")
        notes = []
        if mode == "model":
            try:
                name, args = LocalModelRouter(self.router_url, self.router_model, self.policy.declarations()).route(message)
                return {"tool": name, "arguments": args if isinstance(args, dict) else {}, "router": "model", "notes": notes}
            except ChatError as exc:
                notes.append(f"{exc} Es wurde der Regel-Router verwendet.")
        call = rule_route(message, self._roles())
        return {**call, "router": "rules", "notes": notes}

    def _run(self, tool: str, arguments: dict, *, message: str, session: str, router: str, confirmed: bool = False) -> tuple[Decision, dict | None]:
        decision = self.policy.decide(tool, arguments)
        if not decision.allowed:
            self.policy.audit(decision, session=session, router=router, message=message)
            return decision, None
        if decision.confirmation_required and not confirmed:
            self.policy.audit(decision, session=session, router=router, message=message, executed=False)
            return decision, {"pendingConfirmation": True, "title": f"{tool}: Bestätigung erforderlich",
                              "text": "Diese Funktion schreibt Dateien (WRITE_LOCAL) in den lokalen OneDrive-Ordner. Sie wird erst nach Ihrer Bestätigung ausgeführt.",
                              "items": []}
        result = getattr(self, f"_tool_{tool}")(decision.arguments)
        self.policy.audit(decision, session=session, router=router, message=message, executed=True)
        return decision, result

    def ask(self, message: str, mode: str = "rules", session: str = "") -> dict:
        call = self.route(message, mode)
        message = message.strip()
        base = {"message": message, "router": call["router"], "notes": call["notes"], "answeredAt": now_iso()}
        if call["tool"] == "none":
            return {**base, "call": {"tool": "none", "arguments": {}}, "steps": [], **self._help()}
        steps = []
        if call["tool"] == "search_knowledge" and not call["arguments"].get("status"):
            return {**base, "call": {"tool": call["tool"], "arguments": call["arguments"]}, **self._local_first(call, message, session, steps)}
        decision, result = self._run(call["tool"], call["arguments"], message=message, session=session, router=call["router"])
        steps.append({"tool": call["tool"], "arguments": decision.arguments or call["arguments"], "policy": decision.as_dict()})
        if not decision.allowed:
            return {**base, "call": {"tool": call["tool"], "arguments": call["arguments"]}, "steps": steps, "denied": True,
                    "title": "Vom Security-Policy-System abgelehnt", "text": f"{decision.reason} Es wurde nichts ausgeführt.", "items": []}
        return {**base, "call": {"tool": call["tool"], "arguments": decision.arguments}, "steps": steps, **result}

    def execute_confirmed(self, tool: str, arguments: dict, session: str = "") -> dict:
        """Second step for tools with confirmation_required (export_knowledge)."""
        decision, result = self._run(tool, arguments, message="", session=session, router="confirmed", confirmed=True)
        if not decision.allowed:
            raise PolicyError(decision.reason)
        return {"call": {"tool": tool, "arguments": decision.arguments}, "steps": [{"tool": tool, "arguments": decision.arguments, "policy": decision.as_dict()}],
                "router": "confirmed", "notes": [], "message": "", "answeredAt": now_iso(), **result}

    def _local_first(self, call, message, session, steps) -> dict:
        """1 Released knowledge → 2 other claims → 3 manual → 4 Jira → 5 Confluence → 6 Rovo → stop."""
        args = dict(call["arguments"])
        query = args.get("query", "")
        scope = {"chapter": args["chapter"]} if args.get("chapter") else {}
        chain = [("search_knowledge", {**args, "status": "Released"}),
                 ("search_knowledge", {**args, "status": "Reviewed"}),
                 ("search_knowledge", {**args, "status": "Draft"}),
                 ("search_manual", {k: v for k, v in args.items() if k in ("query", "chapter", "language")}),
                 ("search_jira", {"query": query, **scope}),
                 ("search_confluence", {"query": query, **scope}),
                 ("query_rovo", {"query": query, **scope})]
        for tool, tool_args in chain:
            decision, result = self._run(tool, tool_args, message=message, session=session, router=call["router"])
            found = bool(result and result.get("items"))
            steps.append({"tool": tool, "arguments": decision.arguments or tool_args, "policy": decision.as_dict(), "found": found})
            if found:
                return {"steps": steps, **result}
        return {"steps": steps, "title": NO_SOURCE,
                "text": "Weder freigegebenes Wissen noch Claims, Handbuch oder interne Quellen (Jira, Confluence, Rovo) enthalten passende Inhalte. "
                        "Es erfolgt kein Rückgriff auf das Internet.", "items": []}

    def _help(self):
        return {"title": "Keine passende Funktion erkannt", "text": "Ich beantworte Fragen über die freigegebenen Funktionen der Tool Registry, z. B.:",
                "items": [{"type": "example", "label": e} for e in ("Was gilt bei Service Contract Cancellation für PC?", "Berechne die Coverage für CH01",
                                                                     "Validiere Kapitel 1", "Zeige unbelegte kritische Claims in CH01",
                                                                     "Welche Evidence gibt es aus Jira?", "Exportiere CH01 als Review-Paket")]}

    # -- tool implementations (read local data; export writes only into the local OneDrive folder) ---------------
    def _allowed(self, chapter_id: str) -> bool:
        chapters = self.policy.allowed_chapters()
        return chapters is None or chapter_id in chapters

    def _index(self):
        data = self.knowledge.load()
        blocks = {k["knowledgeId"]: k for k in data["knowledgeBlocks"]}
        factors = {}
        for ev in data["evidence"]:
            factors[ev["claimId"]] = max(factors.get(ev["claimId"], 0.0), evidence_factor(ev))
        return data, blocks, factors

    @staticmethod
    def _claim_item(claim, factor, score=None):
        return {"type": "claim", "id": claim["claimId"], "chapterId": claim["chapterId"], "questionId": claim["questionId"],
                "label": claim["canonicalStatement"], "role": claim.get("role", ""), "division": claim.get("division", ""),
                "status": STATUS_LABEL.get(claim["validationStatus"], claim["validationStatus"]), "criticality": claim["criticality"],
                "evidence": round(factor, 2), **({"score": round(score, 2)} if score is not None else {})}

    def _query_tokens(self, query):
        normalized, _ = self.rules.apply(query)
        return object_tokens(normalized) | object_tokens(query)

    def _tool_search_knowledge(self, args):
        data, blocks, factors = self._index()
        query = self._query_tokens(args["query"])
        wanted = STATUS_MAP.get(args.get("status", ""), "")
        items = []
        if wanted in ("", "CONFIRMED"):  # the maintained rule set counts as released knowledge
            term = args["query"].casefold()
            for rule in self.rules.list():
                if rule["category"] in ("abbreviation", "explanation", "synonym", "naming") and \
                        re.search(r"(?<![\w])" + re.escape(rule["source"].casefold()) + r"(?![\w])", term):
                    label = {"abbreviation": f"{rule['source']} = {rule['target']}", "explanation": f"{rule['source']}: {rule['target']}",
                             "synonym": f"{rule['source']} → kanonisch {rule['target']}",
                             "naming": f"Schreibweise: {rule['target']} (nicht „{rule['source']}“)"}[rule["category"]]
                    items.append({"type": "rule", "id": rule["id"], "label": label, "status": "Released"})
        hits = []
        for claim in data["claims"]:
            if claim["validationStatus"] == "REJECTED" or (wanted and claim["validationStatus"] != wanted) or not self._allowed(claim["chapterId"]):
                continue
            block = blocks.get(claim["knowledgeId"], {})
            if args.get("chapter") and claim["chapterId"] != args["chapter"]:
                continue
            if args.get("role") and claim.get("role") not in (args["role"], ""):
                continue
            if args.get("vehicle_type") and args["vehicle_type"] != "ALL" and claim.get("division") not in (args["vehicle_type"], "BOTH", ""):
                continue
            if args.get("language") and not block.get("text" + args["language"]):
                continue
            overlap = len(query & (object_tokens(claim["canonicalStatement"]) | object_tokens(block.get("topic", ""))))
            if overlap:
                hits.append((overlap / max(1, len(query)) + 0.1 * factors.get(claim["claimId"], 0), claim))
        hits.sort(key=lambda h: -h[0])
        items += [self._claim_item(c, factors.get(c["claimId"], 0.0), s) for s, c in hits[:8]]
        label = args.get("status") or "alle"
        text = f"{len(items)} Treffer mit Status {label}."
        if wanted and wanted != "CONFIRMED" and items:
            text += " Diese Aussagen sind nicht freigegeben – nicht als gesicherte Auskunft verwenden."
        return {"title": f"oneSCM360 Knowledge ({label}): „{args['query']}“", "text": text, "items": items}

    def _tool_search_manual(self, args):
        query = self._query_tokens(args["query"])
        items = []
        for record in self.imports.records(args.get("chapter")):
            if record.get("status") != "COMPLETED" or not self._allowed(record["chapterId"]):
                continue
            if args.get("language") and args["language"] not in record.get("language", ""):
                continue
            for q in record.get("questions", []):
                if args.get("question") and q["questionId"] != args["question"]:
                    continue
                text = q.get("normalizedText") or ""
                if not text:
                    continue
                overlap = len(query & (object_tokens(text) | object_tokens(q.get("title", ""))))
                if overlap or args.get("question"):
                    items.append((overlap, {"type": "manual", "id": q["questionId"], "chapterId": record["chapterId"],
                                            "label": f"{q.get('title', '')}: {text[:280]}{' …' if len(text) > 280 else ''}",
                                            "status": record.get("validationStatus", "")}))
        items.sort(key=lambda x: -x[0])
        result = [i for _, i in items[:8]]
        return {"title": f"Handbuch: „{args['query']}“", "text": f"{len(result)} Abschnitt(e) aus importierten Kapiteltexten.", "items": result}

    def _evidence_search(self, source_type, args, label):
        data, _blocks, _factors = self._index()
        claims = {c["claimId"]: c for c in data["claims"]}
        query = self._query_tokens(args["query"]) if args.get("query") else set()
        items = []
        for ev in data["evidence"]:
            claim = claims.get(ev["claimId"])
            if ev.get("sourceType") != source_type or not claim or not self._allowed(claim["chapterId"]):
                continue
            if args.get("chapter") and claim["chapterId"] != args["chapter"]:
                continue
            if args.get("jira_key") and ev.get("jiraKey", "").upper() != args["jira_key"].upper():
                continue
            haystack = object_tokens(" ".join([ev.get("excerpt", ""), ev.get("sourceTitle", ""), claim["canonicalStatement"]]))
            if query and not (query & haystack):
                continue
            items.append({"type": "evidence", "id": ev["evidenceId"], "claimId": claim["claimId"], "chapterId": claim["chapterId"],
                          "label": f"{ev.get('jiraKey') or ev.get('sourceTitle') or ev.get('sourceURL')}: {ev.get('excerpt', '')[:200]}",
                          "status": ev["evidenceStatus"], "criticality": ev["evidenceStrength"], "evidence": evidence_factor(ev)})
        note = f"Die interne {label}-Schnittstelle ist noch nicht konfiguriert. Ergebnis aus lokal importierter {label}-Evidence."
        return {"title": f"{label}: {args.get('jira_key') or args.get('query') or 'alle'}", "text": f"{note} {len(items)} Treffer.",
                "items": items[:20], "connector": False}

    def _tool_search_jira(self, args):
        return self._evidence_search("JIRA", args, "Jira")

    def _tool_search_confluence(self, args):
        return self._evidence_search("CONFLUENCE", args, "Confluence")

    def _tool_query_rovo(self, args):
        return self._evidence_search("ROVO", args, "Rovo")

    def _tool_get_claims(self, args):
        data, _blocks, factors = self._index()
        if args.get("claim_id"):
            claim = next((c for c in data["claims"] if c["claimId"].upper() == args["claim_id"].upper() and self._allowed(c["chapterId"])), None)
            if not claim:
                return {"title": f"Claim {args['claim_id']}", "text": "Dieser Claim existiert nicht oder ist nicht freigegeben.", "items": []}
            item = self._claim_item(claim, factors.get(claim["claimId"], 0.0))
            return {"title": f"Claim {claim['claimId']}", "text": f"{claim['chapterId']} {claim['questionId']} · {item['status']} · Evidence {item['evidence']:.2f}",
                    "items": [item], "link": {"tab": "claims", "chapterId": claim["chapterId"], "claimId": claim["claimId"]}}
        wanted = STATUS_MAP.get(args.get("status", ""), "")
        result = []
        for claim in data["claims"]:
            factor = factors.get(claim["claimId"], 0.0)
            if not self._allowed(claim["chapterId"]) or (args.get("chapter") and claim["chapterId"] != args["chapter"]):
                continue
            if (wanted and claim["validationStatus"] != wanted) or (not wanted and claim["validationStatus"] == "REJECTED"):
                continue
            if args.get("role") and claim.get("role") != args["role"]:
                continue
            if args.get("criticality") and claim["criticality"] != args["criticality"]:
                continue
            if args.get("vehicle_type") and args["vehicle_type"] != "ALL" and claim.get("division") not in (args["vehicle_type"], "BOTH"):
                continue
            evidence = args.get("evidence")
            if (evidence == "missing" and factor >= 0.9) or (evidence == "indirect" and not 0 < factor < 0.9) or (evidence == "direct" and factor < 0.9):
                continue
            result.append(self._claim_item(claim, factor))
        labels = {"missing": "ohne direkte Evidence", "indirect": "nur indirekte Evidence", "direct": "mit direkter Evidence"}
        parts = [args.get("chapter", ""), args.get("status", ""), args.get("criticality", ""), args.get("role", ""), args.get("vehicle_type", ""),
                 labels.get(args.get("evidence", ""), "")]
        return {"title": "Claims " + " · ".join(p for p in parts if p), "text": f"{len(result)} Claim(s).", "items": result[:30]}

    def _tool_get_evidence(self, args):
        evidence = [e for e in self.knowledge.evidence(claim_id=args.get("claim_id"), chapter_id=args.get("chapter"))
                    if self._allowed(e.get("chapterId", "")) and (not args.get("source_type") or e["sourceType"] == args["source_type"])
                    and (not args.get("strength") or e["evidenceStrength"] == args["strength"])]
        items = [{"type": "evidence", "id": e["evidenceId"], "claimId": e["claimId"], "chapterId": e.get("chapterId", ""),
                  "label": f"{e['sourceType']} · {e.get('jiraKey') or e.get('sourceTitle') or e.get('sourceURL')}",
                  "status": e["evidenceStatus"], "criticality": e["evidenceStrength"], "evidence": e["factor"]} for e in evidence[:30]]
        scope = args.get("claim_id") or args.get("chapter") or "alle Claims"
        return {"title": f"Evidence: {scope}", "text": f"{len(evidence)} Nachweis(e).", "items": items}

    def _tool_calculate_coverage(self, args):
        chapter = self.chapters.get(args["chapter"])
        cov = self.compute_coverage(args["chapter"])
        details = cov["details"]
        division = details.get("divisionScores", {})
        values = {"questions": ("Questions", cov["questionCoverage"]), "claims": ("Claims freigegeben", details.get("claimsReleased", 0.0)),
                  "evidence": ("Evidence", cov["evidenceCoverage"]), "roles": ("Roles", cov["roleCoverage"]),
                  "PC": ("PC", division.get("PC", 0.0)), "VAN": ("VAN", division.get("VAN", 0.0)),
                  "CV": ("CV (nicht in Readiness)", division.get("CV", 0.0)), "PI_status": ("PI-Status", cov["piCoverage"])}
        dims = args.get("dimensions") or list(values)
        items = [{"type": "metric", "label": values[d][0], "value": values[d][1]} for d in dims]
        return {"title": f"Coverage {chapter['chapterId']} – {chapter['title']}",
                "text": f"Gate {cov['gate']} · Readiness {cov['readiness']:.1f} %. {cov['gateReason']} (Berechnung durch den deterministischen Coverage-Service.)",
                "items": items, "gate": cov["gate"], "link": {"tab": "coverage", "chapterId": chapter["chapterId"]}}

    def _tool_validate_chapter(self, args):
        chapter = self.chapters.get(args["chapter"])
        cov = self.compute_coverage(args["chapter"])
        findings = []
        records = self.imports.records(args["chapter"])
        if not any(r.get("status") == "COMPLETED" for r in records):
            findings.append(("BLOCKED", "Kein Import für dieses Kapitel."))
        for record in records:
            for err in record.get("errors", []):
                if record.get("status") == "FAILED":  # a failed run delivered no data – a hint, not a blocker
                    findings.append(("WARNING", f"Import {record['importId']} fehlgeschlagen: {err['message']}"))
                else:
                    findings.append(("BLOCKED", f"Import {record['importId']}: {err['message']}"))
            for warning in record.get("warnings", []):
                findings.append(("WARNING", f"Import {record['importId']}: {warning}"))
            for table in record.get("tables", []):
                if table.get("reviewRequired"):
                    findings.append(("WARNING", f"Tabelle {table['tableId']} ohne Quellfrage – Review nötig."))
        for blocker in cov["blockers"]:
            findings.append(("BLOCKED", blocker))
        for conflict in self.knowledge.conflicts(args["chapter"]):
            if conflict["status"] == "OPEN" and conflict["severity"] != "CRITICAL":
                findings.append(("WARNING", f"Offener Konflikt {conflict['conflictId']} ({conflict['type']})."))
        answered = {c["questionId"] for c in self.knowledge.claims(chapter_id=args["chapter"]) if c["validationStatus"] != "REJECTED"}
        for q in chapter["questions"]:
            if q["criticality"] == "CRITICAL" and q["questionId"] not in answered:
                findings.append(("WARNING", f"Kritische Frage {q['questionId']} ({q['title']}) unbeantwortet."))
        verdict = "BLOCKED" if any(s == "BLOCKED" for s, _ in findings) else "WARNINGS" if findings else "OK"
        items = [{"type": "finding", "label": text, "status": status} for status, text in findings[:40]]
        return {"title": f"Validierung {chapter['chapterId']}: {verdict}",
                "text": f"{len(findings)} Befund(e) nach lokalem Regelwerk. Gate {cov['gate']}.", "items": items, "gate": verdict,
                "link": {"tab": "coverage", "chapterId": chapter["chapterId"]}}

    def _tool_export_knowledge(self, args):
        fmt = args.get("format", "review_package")
        result = self.export_chapter(args["chapter"], {"json": "json", "csv": "csv"}.get(fmt, "package"))
        return {"title": f"Export {args['chapter']} ({fmt})",
                "text": f"{len(result['files'])} Datei(en) lokal im OneDrive-Ordner bereitgestellt. Cloudstatus: {result['cloudStatus']}.",
                "items": [{"type": "file", "label": f} for f in result["files"][:30]], "link": {"tab": "sync"}}

    # -- evaluation & training data ---------------------------------------------------------
    def evaluate(self, mode: str = "rules") -> dict:
        cases = json.loads(self.eval_path.read_text(encoding="utf-8"))["cases"]
        results = []

        def same(actual, wanted):
            if isinstance(wanted, list):
                return sorted(map(str.casefold, actual or [])) == sorted(map(str.casefold, wanted))
            return str(actual or "").casefold() == str(wanted).casefold()

        for case in cases:
            try:
                call = self.route(case["message"], mode)
            except ChatError as exc:
                call = {"tool": "error", "arguments": {}, "router": mode, "notes": [str(exc)]}
            decision = self.policy.decide(call["tool"], call["arguments"]) if call["tool"] not in ("none", "error") else None
            args = decision.arguments if decision and decision.allowed else call["arguments"]
            expected = case.get("arguments", {})
            policy_result = decision.as_dict()["result"] if decision else "NONE"
            ok = call["tool"] == case["tool"] and all(same(args.get(k), v) for k, v in expected.items())
            if case.get("policy"):
                ok = ok and policy_result == case["policy"]
            results.append({"message": case["message"], "expected": {"tool": case["tool"], "arguments": expected, "policy": case.get("policy", "")},
                            "actual": {"tool": call["tool"], "arguments": args, "policy": policy_result}, "router": call["router"], "ok": ok})
        return {"mode": mode, "passed": sum(r["ok"] for r in results), "total": len(results), "results": results}

    def feedback(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ChatError("Ungültiges Feedback.")
        message = str(payload.get("message", "")).strip()[:MAX_MESSAGE]
        tool_name = str(payload.get("tool", ""))
        tool = self.policy.tool(tool_name)
        if not message:
            raise ChatError("Die Frage fehlt.")
        if tool is None:
            raise ChatError("Nur Funktionen aus der Tool Registry sind als Trainingsbeispiel zulässig.")
        arguments = payload.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise ChatError("Ungültige Parameter.")
        if not arguments:
            derived = rule_route(message, self._roles())["arguments"]
            props = tool["parameters"]["properties"]
            arguments = {k: v for k, v in derived.items() if k in props}
            if "query" in props and "query" not in arguments:
                arguments["query"] = _clean_query(message)
        try:
            arguments = self.policy.validate_arguments(tool, arguments)
        except PolicyError as exc:
            raise ChatError(f"{exc} Bitte die Parameter ergänzen.") from exc
        entry = {"user_content": message, "tool_name": tool_name, "tool_arguments": arguments,
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
        """Template examples over chapters, roles and vehicle types – only registered tools."""
        ex = []
        for chapter in self.chapters.list():
            cid, nn = chapter["chapterId"], chapter["chapterId"][2:]
            ex += [(f"Berechne die Coverage für {cid}", "calculate_coverage", {"chapter": cid}),
                   (f"Wie weit ist Kapitel {int(nn)}?", "calculate_coverage", {"chapter": cid}),
                   (f"Prüfe {cid} auf PI-Relevanz", "calculate_coverage", {"chapter": cid, "dimensions": ["PI_status"]}),
                   (f"Wie ist die Evidence-Abdeckung in {cid}?", "calculate_coverage", {"chapter": cid, "dimensions": ["evidence"]}),
                   (f"Validiere {cid}", "validate_chapter", {"chapter": cid}),
                   (f"Warum ist {cid} blockiert?", "validate_chapter", {"chapter": cid}),
                   (f"Zeige unbelegte Claims in {cid}", "get_claims", {"chapter": cid, "evidence": "missing"}),
                   (f"Welche Claims in {cid} sind freigegeben?", "get_claims", {"chapter": cid, "status": "Released"}),
                   (f"Welche Evidence gibt es in {cid}?", "get_evidence", {"chapter": cid}),
                   (f"Was steht im Handbuch zu {nn}-F01?", "search_manual", {"query": "Handbuch", "chapter": cid, "question": f"{nn}-F01"}),
                   (f"Exportiere {cid} als Review-Paket", "export_knowledge", {"chapter": cid, "format": "review_package"})]
        for role in self._roles():
            ex.append((f"Welche Claims betreffen die Rolle {role['name']}?", "get_claims", {"role": role["id"]}))
        for vehicle in ("PC", "VAN", "CV"):
            ex.append((f"Was gilt bei Service Contract Cancellation für {vehicle}?", "search_knowledge",
                       {"query": "Service Contract Cancellation", "vehicle_type": vehicle}))
        for rule in self.rules.list():
            if rule["category"] in ("abbreviation", "explanation"):
                ex.append((f"Was bedeutet {rule['source']}?", "search_knowledge", {"query": rule["source"]}))
        ex += [("Was sagt Jira zu ONESCM-123?", "search_jira", {"jira_key": "ONESCM-123"}),
               ("Suche in Confluence nach dem Freigabeprozess für Templates", "search_confluence", {"query": "Freigabeprozess Templates"}),
               ("Frag Rovo nach den PI17 Änderungen", "query_rovo", {"query": "PI17 Änderungen"})]
        return [{"user_content": u, "tool_name": t, "tool_arguments": a, "source": "template"} for u, t, a in ex]

    def training_data(self, fmt: str = "notebook") -> str:
        rows = self.seed_examples() + [e for e in self._feedback_entries() if e.get("correct", True)]
        evaluation = {c["message"].casefold() for c in json.loads(self.eval_path.read_text(encoding="utf-8"))["cases"]}
        rows = [r for r in rows if r["user_content"].casefold() not in evaluation and self.policy.tool(r["tool_name"])]
        declarations = [{"type": "function", "function": d} for d in self.policy.declarations()]
        lines = []
        for row in rows:
            if fmt == "messages":
                record = {"messages": [
                    {"role": "developer", "content": "You are a model that can do function calling with the following functions"},
                    {"role": "user", "content": row["user_content"]},
                    {"role": "assistant", "tool_calls": [{"type": "function", "function": {"name": row["tool_name"], "arguments": row["tool_arguments"]}}]}],
                    "tools": declarations}
            else:
                record = {"user_content": row["user_content"], "tool_name": row["tool_name"],
                          "tool_arguments": json.dumps(row["tool_arguments"], ensure_ascii=False)}
            lines.append(json.dumps(record, ensure_ascii=False))
        return "\n".join(lines) + "\n"
