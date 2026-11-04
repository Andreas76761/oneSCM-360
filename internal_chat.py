"""Internal, citation-first chat: answers are verified extracts, never reader content."""
import json
import re
from collections import Counter

import local_model
import publication
from knowledge_review import digest, normalized, signals

QUESTION_WORDS = set("wie was wann warum welche welcher welches wer wo kann können darf dürfen ist sind wird werden bitte mir ich du es das und damit dazu dabei how what when why which who where can could please tell me about the a an is are do does".split())


def words(text):
    return set(w for w in re.findall(r"\w{3,}", text.casefold()) if w not in QUESTION_WORDS)


class InternalChat:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS internal_chats(id TEXT PRIMARY KEY,revision INTEGER,payload TEXT)")

    def profile(self, data):
        from app import Invalid, clean_text, choice, ROLES, LANGUAGES
        p = {"role": choice(data.get("role"), ROLES, "Rollenbezug"),
             "market": clean_text(data.get("market", ""), "Land", 100).strip(),
             "language": choice(data.get("language"), LANGUAGES, "Sprache"),
             "division": choice(data.get("division", "Beide"), ["Van", "PC", "Beide"], "Sparte"),
             "as_of": publication.iso_date(data.get("as_of", ""), "Stichtag", optional=False),
             "environment": choice(data.get("environment", "prod"), ["prod", "preprod"], "Umgebung")}
        if not p["market"]:
            raise Invalid("Land angeben; * sucht ausschließlich allgemein gültige FAQ.")
        return p

    @staticmethod
    def eligible(entry, p):
        if entry["status"] != "Freigegeben" or not entry["chatbot_enabled"] or not entry["answer"].strip():
            return False
        if entry["language"] != p["language"] or entry["roles"] and p["role"] not in entry["roles"]:
            return False
        markets = {m.casefold() for m in entry["markets"]}
        if markets and "*" not in markets and p["market"].casefold() not in markets:
            return False
        divisions = entry.get("divisions", [])
        if divisions and (p["division"] not in divisions if p["division"] != "Beide" else set(divisions) != {"Van", "PC"}):
            return False
        rule = publication.effective(entry.get("validity", []), p)
        return rule["matches"] and rule["state"] in [None, "Freigegeben"]

    def _entries(self, db):
        return [json.loads(r[0]) for r in db.execute("SELECT payload FROM internal_entries ORDER BY id")]

    def _session(self, sid, db):
        from app import Invalid
        row = db.execute("SELECT payload FROM internal_chats WHERE id=?", (sid,)).fetchone()
        if not row:
            raise Invalid("Interner Chat nicht gefunden.")
        return json.loads(row[0])

    def view(self, session, db):
        current = {e["id"]: e for e in self._entries(db)}
        corpus = digest([e for e in current.values() if self.eligible(e, session["profile"])])
        for turn in session["turns"]:
            for cite in turn["citations"]:
                entry = current.get(cite["id"])
                cite["stale"] = not entry or entry["revision"] != cite["revision"] or not self.eligible(entry, session["profile"])
            turn["stale"] = any(c["stale"] for c in turn["citations"]) or turn.get("corpus_fingerprint", corpus) != corpus
        return session

    def listing(self):
        with self.store.connect() as db:
            return [{k: s[k] for k in ["id", "revision", "title", "profile", "updated"]} for (raw,) in db.execute("SELECT payload FROM internal_chats ORDER BY rowid DESC LIMIT 100") for s in [json.loads(raw)]]

    def get(self, sid):
        with self.store.connect() as db:
            return self.view(self._session(sid, db), db)

    def ask(self, data):
        from app import Invalid, Conflict, clean_text, choice, now, uid
        question = clean_text(data.get("question", ""), "Frage", 2000).strip()
        if len(question) < 3:
            raise Invalid("Eine konkrete Frage eingeben.")
        profile = self.profile(data.get("profile", {}))
        mode = choice(data.get("mode", "extractive"), ["extractive", "ollama"], "Chatmodus")
        with self.store.connect() as db:
            session = self._session(data["id"], db) if data.get("id") else {"id": uid(), "revision": 0, "title": question[:100], "profile": profile, "turns": []}
            if session["profile"] != profile:
                raise Conflict("Für ein anderes Profil einen neuen Chat beginnen.")
            if data.get("id") and (type(data.get("revision")) is not int or session["revision"] != data["revision"]):
                raise Conflict("Chat wurde inzwischen geändert. Neu laden.")
            if len(session["turns"]) >= 50:
                raise Invalid("Nach 50 Fragen einen neuen Chat beginnen.")
            entries = [e for e in self._entries(db) if self.eligible(e, profile)]
        snapshot = digest(entries)
        query = question
        if data.get("followup") is True and session["turns"]:
            query = session["turns"][-1]["question"] + " " + question
        query_words = words(query)
        frequency = Counter(w for e in entries for w in words(" ".join([e["title"], e["question"], *e["keywords"], *e["labels"]])))
        ranked = []
        for entry in entries:
            focus = words(" ".join([entry["title"], entry["question"], *entry["keywords"], *entry["labels"]]))
            matched = query_words & (focus | words(entry["answer"]))
            if not matched or len(matched) / max(1, len(query_words)) < .25:
                continue
            score = sum((3 if w in focus else 1) / (1 + frequency[w]) for w in matched)
            ranked.append((score, entry))
        ranked.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
        candidates = [e for _, e in ranked[:8]]
        conflicts = []
        for a in candidates:
            for _, b in ranked:
                qa, qb = words(a["question"]), words(b["question"])
                same_question = normalized(a["question"]) == normalized(b["question"])
                close = len(qa & qb) / max(1, len(qa | qb)) >= .8
                if (same_question and normalized(a["answer"]) != normalized(b["answer"])) or close and signals(a["answer"], b["answer"]) and normalized(a["answer"]) != normalized(b["answer"]):
                    conflicts.extend([a, b])
        status, chosen = "belegt", []
        if conflicts:
            status = "widersprüchlich"
            chosen = [(e, e["answer"]) for e in list({e["id"]: e for e in conflicts}.values())[:10]]
        elif not candidates:
            status = "keine_belege"
        elif mode == "extractive":
            chosen = [(entry, entry["answer"]) for entry in candidates[:3]]
        else:
            # The model selects literal supporting passages; free generated claims
            # cannot pass validation merely by attaching a plausible citation ID.
            payload = {"question": query, "profile": profile, "evidence": [{"id": e["id"], "question": e["question"], "answer": e["answer"][:12000]} for e in candidates[:5]]}
            value = local_model.ask(data.get("model", ""), "Beantworte die Frage durch Auswahl passender wörtlicher FAQ-Belege. Antworte ausschließlich als JSON mit selections: Liste von höchstens 3 Objekten mit id und quote. quote muss ein unverändertes, zusammenhängendes Zitat aus answer sein. Keine eigene Formulierung, keine ergänzten Aussagen. Bei fehlenden Belegen selections: [].", payload)
            selections = value.get("selections")
            if not isinstance(selections, list) or len(selections) > 3:
                raise Invalid("KI lieferte keine gültige Belegauswahl.")
            evidence = {e["id"]: e for e in candidates[:5]}
            seen = set()
            for selection in selections:
                if not isinstance(selection, dict):
                    raise Invalid("Ungültiger KI-Beleg.")
                eid = selection.get("id")
                quote = clean_text(selection.get("quote", ""), "Belegtext", 12000).strip()
                if not isinstance(eid, str) or eid not in evidence or eid in seen or not quote or quote not in evidence[eid]["answer"][:12000]:
                    raise Invalid("KI-Beleg ist nicht wörtlich in der freigegebenen FAQ enthalten. Antwort verworfen.")
                seen.add(eid)
                # Always retain the complete answer: a literal substring can omit
                # a negation, prerequisite or exception and reverse the meaning.
                chosen.append((evidence[eid], evidence[eid]["answer"]))
            if not chosen:
                status = "keine_belege"
        citations = [{"id": e["id"], "revision": e["revision"], "title": e["title"], "question": e["question"], "quote": quote,
                      "source": e["source"], "updated": e["updated"], "fingerprint": digest([e["question"], e["answer"]]), "anchor": f"internal:{e['id']}@{e['revision']}"} for e, quote in chosen]
        answer = ("Für diese Frage und dieses Profil liegen keine ausreichend passenden freigegebenen FAQ-Belege vor. Bitte Frage präzisieren oder das interne Register ergänzen." if status == "keine_belege" else
                  "Die freigegebenen FAQ enthalten abweichende Antworten. Keine eindeutige Antwort möglich; die folgenden Belege im internen Register fachlich klären." if status == "widersprüchlich" else
                  "\n\n".join(f"[{i}] {quote}" for i, (_, quote) in enumerate(chosen, 1)))
        turn = {"id": uid(), "created": now(), "question": question, "context_query": query, "status": status, "answer": answer,
                "citations": citations, "corpus_fingerprint": snapshot, "method": "Lokale FAQ-Belege" if mode == "extractive" else "Ollama-Belegauswahl", "visibility": "internal_only"}
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if digest([e for e in self._entries(db) if self.eligible(e, profile)]) != snapshot:
                raise Conflict("FAQ-Freigaben oder Inhalte wurden während der Antwort geändert. Frage erneut stellen.")
            existing = db.execute("SELECT revision FROM internal_chats WHERE id=?", (session["id"],)).fetchone()
            if existing and existing[0] != session["revision"]:
                raise Conflict("Chat wurde inzwischen geändert. Neu laden.")
            session["turns"].append(turn)
            session.update(revision=session["revision"]+1, updated=now())
            db.execute("INSERT INTO internal_chats VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,payload=excluded.payload", (session["id"], session["revision"], json.dumps(session, ensure_ascii=False)))
            return self.view(session, db)
