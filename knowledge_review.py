"""Reviewable cross-source contradictions; never silently changes reader content."""
import hashlib
import json
import re
from itertools import combinations

import local_model
import publication
import sources

STATES = ["Offen", "Widerspruch bestätigt", "Kein Widerspruch", "Geklärt", "Nicht mehr anwendbar"]
NEGATION = re.compile(r"\b(?:nicht|kein\w*|nie|ohne|not|no|never|cannot|disabled|verboten|unzulässig|gesperrt)\b", re.I)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def normalized(text):
    return " ".join(re.findall(r"\w+", text.casefold()))


def evidence_snapshot(chunk):
    # Adding a document use does not change the statement that was reviewed.
    return {k: v for k, v in chunk.items() if k != "assignments"} if chunk else None


def signals(left, right):
    """Conservative lexical hints, not an assertion of semantic contradiction."""
    if normalized(left) == normalized(right):
        return {"kind": "Duplikat", "reason": "Die normalisierten Texte sind identisch.", "left_quote": left, "right_quote": right}
    split = lambda text: [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()][:35]
    best = None
    for a, b in ((a, b) for a in split(left) for b in split(right)):
        aw, bw = set(sources.tokens(a)), set(sources.tokens(b))
        shared = aw & bw
        similarity = len(shared) / max(1, len(aw | bw))
        if len(shared) < 2 or similarity < .5:
            continue
        reason = []
        if bool(NEGATION.search(a)) != bool(NEGATION.search(b)):
            reason.append("Ähnliche Aussage mit unterschiedlicher Verneinung/Berechtigung")
        numbers = lambda value: set(re.findall(r"\b\d+(?:[.,]\d+)?\b", re.sub(r"\b[A-Z][A-Z0-9_]*-\d+\b", "", value)))
        an, bn = numbers(a), numbers(b)
        if an and bn and an != bn:
            reason.append("Ähnliche Aussage mit unterschiedlichen Zahlen/Werten")
        if reason and (best is None or similarity > best[0]):
            best = (similarity, {"kind": "Möglicher Widerspruch", "reason": "; ".join(reason) + ". Fachlich prüfen.", "left_quote": a, "right_quote": b})
    return best[1] if best else None


class KnowledgeReview:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS source_context(id TEXT PRIMARY KEY,revision INTEGER,payload TEXT);
                CREATE TABLE IF NOT EXISTS knowledge_reviews(id TEXT PRIMARY KEY,revision INTEGER,payload TEXT);
                CREATE TABLE IF NOT EXISTS knowledge_review_history(id TEXT,revision INTEGER,payload TEXT,PRIMARY KEY(id,revision));
                CREATE TABLE IF NOT EXISTS knowledge_scans(id TEXT PRIMARY KEY,payload TEXT);
            """)

    def context(self, sid, db):
        row = db.execute("SELECT payload FROM source_context WHERE id=?", (sid,)).fetchone()
        return json.loads(row[0]) if row else {"id": sid, "revision": 0, "market": "*", "role": "*", "division": "*", "language": "*", "environment": "*", "from": "", "until": "", "date": ""}

    def contexts(self):
        with self.store.connect() as db:
            return [self.context(sid, db) for (sid,) in db.execute("SELECT id FROM sources")]

    def save_context(self, data):
        from app import Invalid, Conflict, clean_text, choice, ROLES, LANGUAGES
        sid = clean_text(data.get("id"), "Quelle", 100)
        value = {"id": sid, "market": clean_text(data.get("market", "*"), "Land", 100).strip() or "*"}
        for key, values in [("role", ROLES), ("division", ["Van", "PC"]), ("language", LANGUAGES), ("environment", ["preprod", "prod"])]:
            value[key] = choice(data.get(key, "*"), ["*"] + values, key)
        for key in ["from", "until", "date"]:
            value[key] = publication.iso_date(data.get(key, ""), key)
        if value["from"] and value["until"] and value["from"] > value["until"]:
            raise Invalid("Gültigkeitsende liegt vor dem Beginn.")
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM sources WHERE id=?", (sid,)).fetchone():
                raise Invalid("Quelle nicht gefunden.")
            old = self.context(sid, db)
            if type(data.get("revision")) is not int or old["revision"] != data["revision"]:
                raise Conflict("Quellenkontext geändert. Neu laden.")
            value["revision"] = old["revision"] + 1
            db.execute("INSERT INTO source_context VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,payload=excluded.payload", (sid, value["revision"], json.dumps(value, ensure_ascii=False)))
        return value

    def chunk(self, cid, db):
        row = db.execute("SELECT c.id,c.source_id,c.revision,c.text,c.location,c.labels,s.name,s.origin,s.release,s.uploaded FROM chunks c JOIN sources s ON s.id=c.source_id WHERE c.id=?", (cid,)).fetchone()
        if not row:
            return None
        value = dict(zip(["id", "source_id", "revision", "text", "location", "labels", "name", "origin", "release", "uploaded"], row))
        value["labels"] = json.loads(value["labels"])
        value["context"] = self.context(value["source_id"], db)
        value["assignments"] = [{"outline_id": o, "chapter_id": c} for o, c in db.execute("SELECT outline_id,chapter_id FROM assignments WHERE chunk_id=? ORDER BY outline_id,chapter_id", (cid,))]
        return value

    @staticmethod
    def overlap(a, b):
        x, y = a["context"], b["context"]
        if any(x[k] != "*" and y[k] != "*" and x[k].casefold() != y[k].casefold() for k in ["market", "role", "division", "language", "environment"]):
            return False
        if x["until"] and y["from"] and x["until"] < y["from"] or y["until"] and x["from"] and y["until"] < x["from"]:
            return False
        ar, br = set(a["labels"].get("roles", [])), set(b["labels"].get("roles", []))
        return not (ar and br and not ar.intersection(br))

    def _record(self, a, b, suggestion, method, db):
        from app import uid, now
        signature = digest([sorted([evidence_snapshot(a), evidence_snapshot(b)], key=lambda c: c["id"]), suggestion["kind"]])
        for (raw,) in db.execute("SELECT payload FROM knowledge_reviews"):
            old = json.loads(raw)
            if old["signature"] == signature:
                return old
        row = {"id": uid(), "revision": 1, "created": now(), "updated": now(), "left": a, "right": b,
               "signature": signature, "method": method, **suggestion, "status": "Offen", "decision": "", "preferred": ""}
        if a["release"] and b["release"] and a["release"] != b["release"] and row["kind"] != "Duplikat":
            row["reason"] += " Unterschiedliche Release-Angaben: möglicherweise beabsichtigte Versionsänderung."
        raw = json.dumps(row, ensure_ascii=False)
        db.execute("INSERT INTO knowledge_reviews VALUES(?,?,?)", (row["id"], 1, raw))
        db.execute("INSERT INTO knowledge_review_history VALUES(?,?,?)", (row["id"], 1, raw))
        return row

    def scan(self, data):
        from app import Invalid, uid, now
        ids = data.get("sources", [])
        if not isinstance(ids, list) or not 2 <= len(ids) <= 20 or any(not isinstance(s, str) for s in ids) or len(set(ids)) != len(ids):
            raise Invalid("2–20 unterschiedliche Quellen auswählen.")
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = []
            for sid in ids:
                if not db.execute("SELECT 1 FROM sources WHERE id=?", (sid,)).fetchone():
                    raise Invalid("Eine ausgewählte Quelle fehlt.")
                for (cid,) in db.execute("SELECT id FROM chunks WHERE source_id=? ORDER BY ordinal", (sid,)):
                    rows.append(self.chunk(cid, db))
                    if len(rows) > 300:
                        raise Invalid("Scan auf maximal 300 Chunks aufteilen.")
            results, compared, separated = [], 0, 0
            # Candidate generation avoids sentence comparisons for unrelated chunks.
            words = {c["id"]: set(sources.tokens(c["text"])) for c in rows}
            for a, b in combinations(rows, 2):
                if a["source_id"] == b["source_id"]:
                    continue
                if not self.overlap(a, b):
                    separated += 1
                    continue
                compared += 1
                aw, bw = words[a["id"]], words[b["id"]]
                if len(aw & bw) < 2 or len(aw & bw) / max(1, min(len(aw), len(bw))) < .3:
                    continue
                hint = signals(a["text"], b["text"])
                if hint:
                    results.append(self._record(a, b, hint, "Lokale Textregeln", db)["id"])
                    if len(results) > 500:
                        raise Invalid("Mehr als 500 Treffer. Quellen enger auswählen; Scan wurde nicht gespeichert.")
            report = {"id": uid(), "created": now(), "sources": ids, "chunks": len(rows), "compared": compared, "separated": separated,
                      "reviews": results, "method": "Lokale Textregeln", "note": "Keine Vollständigkeitsgarantie. Zahlen, Verneinung und Duplikate werden heuristisch geprüft; fachliche Prüfung erforderlich."}
            db.execute("INSERT INTO knowledge_scans VALUES(?,?)", (report["id"], json.dumps(report, ensure_ascii=False)))
        return report

    def inspect(self, data):
        from app import Invalid, Conflict, clean_text
        with self.store.connect() as db:
            a, b = [self.chunk(clean_text(data.get(k), "Chunk", 100), db) for k in ["left_id", "right_id"]]
        if not a or not b or a["source_id"] == b["source_id"]:
            raise Invalid("Zwei Textstellen aus verschiedenen vorhandenen Quellen wählen.")
        if not self.overlap(a, b):
            raise Invalid("Die ausgewählten Quellen haben getrennte Gültigkeitsbereiche; Kontext zuerst prüfen.")
        if data.get("mode", "manual") == "ollama":
            result = local_model.ask(data.get("model", ""), "Prüfe die beiden Textstellen auf einen möglichen inhaltlichen Widerspruch. Erfinde keinen Befund. Antworte als JSON mit reason (Begründung), left_quote und right_quote (jeweils nichtleeres wörtliches Zitat aus der zugehörigen Textstelle). Auch ein fehlender Widerspruch ist zu begründen; Menschen entscheiden anschließend.", {"left": {k:a[k] for k in ["text", "context", "release"]}, "right": {k:b[k] for k in ["text", "context", "release"]}})
            hint = {"kind": "KI-Prüfvorschlag", "reason": clean_text(result.get("reason"), "KI-Begründung", 3000)}
            for key, chunk in [("left_quote", a), ("right_quote", b)]:
                quote = clean_text(result.get(key), "Belegzitat", 1600).strip()
                if not quote or quote not in chunk["text"]:
                    raise Invalid("KI-Beleg ist nicht wörtlich in der Quelle vorhanden. Ergebnis verworfen.")
                hint[key] = quote
            method = "Ollama: " + data["model"]
        elif data.get("mode", "manual") == "manual":
            reason = clean_text(data.get("reason", ""), "Prüfgrund", 3000).strip()
            if not reason:
                raise Invalid("Einen Prüfgrund ergänzen.")
            hint = {"kind": "Manueller Prüfpunkt", "reason": reason, "left_quote": a["text"], "right_quote": b["text"]}
            method = "Manuell"
        else:
            raise Invalid("Unbekannter Prüfmodus.")
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if self.chunk(a["id"], db) != a or self.chunk(b["id"], db) != b:
                raise Conflict("Quellen wurden während der Prüfung geändert. Erneut prüfen.")
            return self._record(a, b, hint, method, db)

    def view(self, row, db):
        current = [self.chunk(row[k]["id"], db) for k in ["left", "right"]]
        stale = any(evidence_snapshot(new) != evidence_snapshot(row[k]) for new, k in zip(current, ["left", "right"]))
        retired = row["status"] == "Nicht mehr anwendbar" and (not all(current) or not self.overlap(*current))
        if retired:
            stale = False
        return {**row, "stale": stale, "effective_status": "Erneut prüfen" if stale else row["status"],
                "affected": [dict(outline_id=o, chapter_id=c) for o,c in sorted({(link["outline_id"], link["chapter_id"]) for side in current if side for link in side["assignments"]})]}

    def listing(self, db=None):
        if db is None:
            with self.store.connect() as conn:
                return self.listing(conn)
        rows = [self.view(json.loads(raw), db) for (raw,) in db.execute("SELECT payload FROM knowledge_reviews ORDER BY rowid DESC")]
        current = {tuple(sorted([r["left"]["id"], r["right"]["id"]])): r["id"] for r in reversed(rows) if not r["stale"]}
        for row in rows:
            replacement = current.get(tuple(sorted([row["left"]["id"], row["right"]["id"]])))
            row["superseded_by"] = replacement if replacement and replacement != row["id"] else ""
        return rows

    def decide(self, data):
        from app import Invalid, Conflict, clean_text, choice, now
        status = choice(data.get("status"), STATES, "Entscheidung")
        note = clean_text(data.get("decision", ""), "Entscheidungsbegründung", 5000).strip()
        if not note:
            raise Invalid("Entscheidung begründen; Quellen werden nicht automatisch geändert.")
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            found = db.execute("SELECT payload FROM knowledge_reviews WHERE id=?", (data.get("id"),)).fetchone()
            if not found:
                raise Invalid("Prüfpunkt fehlt.")
            row = json.loads(found[0])
            latest = [self.chunk(row[k]["id"], db) for k in ["left", "right"]]
            can_retire = not all(latest) or not self.overlap(*latest)
            if status == "Nicht mehr anwendbar" and not can_retire:
                raise Invalid("Nur nach Quellenlöschung oder nachweislich getrennten Gültigkeitsbereichen so abschließen. Sonst die aktuelle Aussage fachlich entscheiden.")
            if type(data.get("revision")) is not int or data["revision"] != row["revision"] or self.view(row, db)["stale"] and status != "Nicht mehr anwendbar":
                raise Conflict("Prüfpunkt oder Quellenstand geändert. Textstellen erneut scannen/vergleichen.")
            preferred = choice(data.get("preferred", ""), ["", "left", "right"], "Bevorzugter Beleg")
            row.update(status=status, decision=note, preferred=preferred, revision=row["revision"]+1, updated=now())
            raw = json.dumps(row, ensure_ascii=False)
            db.execute("UPDATE knowledge_reviews SET revision=?,payload=? WHERE id=?", (row["revision"], raw, row["id"]))
            db.execute("INSERT INTO knowledge_review_history VALUES(?,?,?)", (row["id"], row["revision"], raw))
            return self.view(row, db)

    def history(self, rid):
        with self.store.connect() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT payload FROM knowledge_review_history WHERE id=? ORDER BY revision DESC", (rid,))]

    def blockers(self, outline_ids, db):
        return [r for r in self.listing(db) if not r["superseded_by"] and r["kind"] != "Duplikat" and
                (r["stale"] or r["status"] in ["Offen", "Widerspruch bestätigt"]) and
                any(link["outline_id"] in outline_ids for link in r["affected"])]
