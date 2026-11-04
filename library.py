"""Versioned reusable text blocks. Assignments pin an immutable library revision."""
import copy
from contextlib import nullcontext
import json


class Library:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS library(id TEXT PRIMARY KEY, revision INTEGER, payload TEXT);
                CREATE TABLE IF NOT EXISTS library_history(id TEXT, revision INTEGER, payload TEXT, PRIMARY KEY(id, revision));
            """)

    def listing(self):
        with self.store.connect() as db:
            entries = [json.loads(r[0]) for r in db.execute("SELECT payload FROM library ORDER BY rowid DESC")]
        usage = {}
        for o in self.store.all():
            for c in o["chapters"]:
                for b in c["blocks"]:
                    ref = b.get("library_ref")
                    if ref:
                        usage.setdefault(ref["id"], []).append({"outline_id": o["id"], "outline": o["title"],
                            "chapter": c["title"], "revision": ref["revision"]})
        for entry in entries:
            entry["usage"] = usage.get(entry["id"], [])
            translation = entry.get("translation")
            if translation:
                source = next((e for e in entries if e["id"] == translation["source_id"]), None)
                entry["translation_stale"] = not source or source["revision"] != translation["source_revision"]
        return entries

    def snapshot(self, ref):
        from app import Invalid, clean_text
        if not isinstance(ref, dict) or type(ref.get("revision")) is not int:
            raise Invalid("Ungültige Bausteinreferenz.")
        lid = clean_text(ref.get("id"), "Bibliotheks-ID", 100)
        with self.store.connect() as db:
            row = db.execute("SELECT payload FROM library_history WHERE id=? AND revision=?", (lid, ref["revision"])).fetchone()
        if not row:
            raise Invalid("Bausteinrevision nicht gefunden.")
        return json.loads(row[0])

    def save(self, data, connection=None):
        from app import new_outline, chapter, validate_outline, clean_text, boolean, Conflict, Invalid, now
        if type(data.get("revision")) is not int or data["revision"] < 0:
            raise Invalid("Ungültige Bausteinrevision.")
        lid = clean_text(data.get("id"), "Bibliotheks-ID", 100)
        title = clean_text(data.get("title"), "Bausteintitel", 300).strip()
        if not lid or not title:
            raise Invalid("Bausteintitel und Kennung sind erforderlich.")
        block = copy.deepcopy(data.get("block"))
        if not isinstance(block, dict):
            raise Invalid("Baustein fehlt.")
        block.pop("library_ref", None)
        block.pop("assignment", None)
        dummy = new_outline("Validierung")
        dummy["chapters"] = [chapter("Baustein")]
        dummy["chapters"][0]["blocks"] = [block]
        block = validate_outline(dummy)["chapters"][0]["blocks"][0]
        domains = data.get("domains", [])
        valid = {d["id"] for d in self.store.get_catalog()}
        if not isinstance(domains, list) or any(d not in valid for d in domains):
            raise Invalid("Ungültige Bausteindomänen.")
        item = {"id": lid, "revision": data["revision"] + 1, "title": title, "block": block,
                "domains": list(dict.fromkeys(domains)), "tags": clean_text(data.get("tags", ""), "Stichwörter", 2000),
                "archived": boolean(data.get("archived", False), "Archiv"),
                "mandatory_term": boolean(data.get("mandatory_term", False), "Pflichtbegriff"), "updated": now()}
        translation = data.get("translation")
        if translation:
            if not isinstance(translation, dict):
                raise Invalid("Ungültiger Übersetzungsnachweis.")
            source = self.snapshot({"id": translation.get("source_id"), "revision": translation.get("source_revision")})
            if source["id"] == lid or source["block"]["language"] == block["language"]:
                raise Invalid("Sprachfassung muss eine andere Kennung und Zielsprache haben.")
            reviewed = boolean(translation.get("reviewed", False), "Übersetzungsprüfung")
            if block["status"] == "Freigegeben" and not reviewed:
                raise Invalid("Übersetzung vor der Freigabe ausdrücklich fachlich prüfen.")
            item["translation"] = {"source_id": source["id"], "source_revision": source["revision"],
                "source_language": source["block"]["language"], "target_language": block["language"],
                "method": clean_text(translation.get("method", "Manuell"), "Übersetzungsmethode", 200), "reviewed": reviewed}
        with (self.store.connect() if connection is None else nullcontext(connection)) as db:
            if connection is None:
                db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT revision FROM library WHERE id=?", (lid,)).fetchone()
            if (old and old[0] != data["revision"]) or (not old and data["revision"] != 0):
                raise Conflict("Baustein wurde geändert. Bibliothek neu öffnen.")
            raw = json.dumps(item, ensure_ascii=False)
            db.execute("INSERT INTO library VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,payload=excluded.payload", (lid,item["revision"],raw))
            db.execute("INSERT INTO library_history VALUES(?,?,?)", (lid,item["revision"],raw))
        return item

    def resolve(self, data):
        """Ignore edits to referenced canonical fields; only narrower use rules survive."""
        data = copy.deepcopy(data)
        for c in data.get("chapters", []):
            for i, b in enumerate(c.get("blocks", [])):
                if b.get("library_ref"):
                    entry = self.snapshot(b["library_ref"])
                    canonical = entry["block"]
                    canonical.update(id=b["id"], library_ref=b["library_ref"],
                                     library_title=entry["title"], assignment=b.get("assignment", {}), note=b.get("note", ""))
                    if entry.get("translation"):
                        canonical["translation"] = entry["translation"]
                    c["blocks"][i] = canonical
        return data

    def collection(self, data, chapter_id):
        """Preview eligible central glossary/FAQ revisions; commit remains an outline edit."""
        from app import validate_outline, Invalid, uid, compose
        data = validate_outline(self.resolve(data))
        target = next((c for c in data["chapters"] if c["id"] == chapter_id), None)
        if not target or target["config"]["generator"] not in ["Glossar", "FAQ"]:
            raise Invalid("Bitte als Kapitelgenerator Glossar oder FAQ auswählen.")
        kind = "Glossarbegriff" if target["config"]["generator"] == "Glossar" else "FAQ"
        domains = {m["target_id"] for c in data["chapters"] for m in c["mappings"] if m["active"]} if data["mapping_enabled"] else set()
        targets = {d["id"]: d for d in self.store.get_catalog()}
        domains |= {targets[d]["parent_id"] for d in list(domains) if d in targets and targets[d]["parent_id"]}
        existing = {b["library_ref"]["id"] for b in target["blocks"] if b.get("library_ref")}
        selected = []
        for entry in self.listing():
            if entry["archived"] or entry["block"].get("content_kind") != kind or entry["id"] in existing:
                continue
            if entry["domains"] and not domains.intersection(entry["domains"]) and not (kind == "Glossarbegriff" and entry["mandatory_term"]):
                continue
            b = {**entry["block"], "id": uid(), "library_ref": {"id": entry["id"], "revision": entry["revision"]}, "library_title": entry["title"]}
            trial = copy.deepcopy(data)
            trial["chapters"] = [{**target, "level": 1, "blocks": [b]}]
            if compose(trial, data["profile"])["chapters"][0]["blocks"]:
                selected.append(b)
        selected.sort(key=lambda b: b["library_title"].casefold())
        if len(target["blocks"]) + len(selected) > 100:
            raise Invalid("Die Zusammenstellung überschreitet 100 Bausteine; bitte Domänen und Profil einschränken.")
        return {"blocks": selected, "kind": kind}
