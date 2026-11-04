"""Atomic, reviewed promotion of documentation snapshots; no remote system deployment."""
import copy
import json
from datetime import date

import editorial
import publication
from knowledge_review import digest


def profile_key(outline):
    p = outline["profile"]
    return " / ".join([p[k].casefold() for k in ["market", "role", "division", "language", "scope"]] + [outline["metadata"]["document_type"]])


class Releases:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS release_packages(id TEXT PRIMARY KEY,revision INTEGER,payload TEXT);
                CREATE TABLE IF NOT EXISTS release_events(id TEXT PRIMARY KEY,package_id TEXT,created TEXT,payload TEXT);
                CREATE TABLE IF NOT EXISTS production_state(singleton INTEGER PRIMARY KEY CHECK(singleton=1),payload TEXT);
            """)
            db.execute("INSERT OR IGNORE INTO production_state VALUES(1,?)", (json.dumps({"revision": 0, "package_id": "", "version": "", "date": "", "members": []}),))

    def active(self, db):
        return json.loads(db.execute("SELECT payload FROM production_state WHERE singleton=1").fetchone()[0])

    def get(self, pid, db):
        from app import Invalid
        row = db.execute("SELECT payload FROM release_packages WHERE id=?", (pid,)).fetchone()
        if not row:
            raise Invalid("Releasepaket nicht gefunden.")
        return json.loads(row[0])

    def listing(self):
        with self.store.connect() as db:
            return {"active": self.active(db), "packages": [json.loads(r[0]) for r in db.execute("SELECT payload FROM release_packages ORDER BY rowid DESC")],
                    "events": [json.loads(r[0]) for r in db.execute("SELECT payload FROM release_events ORDER BY rowid DESC LIMIT 100")]}

    def _outline(self, oid, db):
        from app import Invalid, hydrate_outline
        row = db.execute("SELECT payload FROM outlines WHERE id=?", (oid,)).fetchone()
        if not row:
            raise Invalid("Eine ausgewählte Gliederung fehlt.")
        return hydrate_outline(json.loads(row[0]))

    def _inputs(self, ids, db):
        active = self.active(db)
        outlines = [self._outline(oid, db) for oid in ids]
        linked = [self.store.review.chunk(cid, db) for (cid,) in db.execute(
            "SELECT DISTINCT chunk_id FROM assignments WHERE outline_id IN (" + ",".join("?" for _ in ids) + ") ORDER BY chunk_id", ids)]
        affected = [r for r in self.store.review.listing(db) if any(a["outline_id"] in ids for a in r["affected"])]
        targets = [self._outline(m["outline_id"], db) for m in active["members"]]
        target_links = {m["outline_id"]: list(db.execute("SELECT chunk_id,chapter_id FROM assignments WHERE outline_id=? ORDER BY chunk_id,chapter_id", (m["outline_id"],))) for m in active["members"]}
        return {"active": active, "outlines": outlines, "targets": targets, "chunks": linked,
                "target_links": target_links, "reviews": affected, "taxonomy": db.execute("SELECT revision FROM taxonomy WHERE singleton=1").fetchone()[0]}

    def _event(self, package, action, note, db):
        from app import now, uid
        event = {"id": uid(), "package_id": package["id"], "version": package["version"], "created": now(),
                 "action": action, "note": note, "production": self.active(db)}
        db.execute("INSERT INTO release_events VALUES(?,?,?,?)", (event["id"], package["id"], event["created"], json.dumps(event, ensure_ascii=False)))

    def prepare(self, data):
        from app import Invalid, Conflict, clean_text, now, uid, validate_outline, compose, compare_outlines
        ids = data.get("sources", [])
        if not isinstance(ids, list) or not 1 <= len(ids) <= 50 or any(not isinstance(i, str) for i in ids) or len(set(ids)) != len(ids):
            raise Invalid("1–50 unterschiedliche gespeicherte Preprod-Gliederungen auswählen.")
        version = clean_text(data.get("version"), "Releaseversion", 60).strip()
        if not version:
            raise Invalid("Releaseversion fehlt.")
        at = publication.iso_date(data.get("date", ""), "Prod-Termin", optional=False)
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = self.get(data["id"], db) if data.get("id") else None
            if old and (old["status"] != "In Prüfung" or type(data.get("revision")) is not int or data["revision"] != old["revision"]):
                raise Conflict("Releasepaket geändert oder bereits aktiviert. Neu laden.")
            inputs = self._inputs(ids, db)
            active = inputs["active"]
            previous = {m["key"]: m for m in active["members"]}
            keys, members, blockers, warnings = set(), [], [], []
            if active["date"] and at < active["date"]:
                blockers.append("Prod-Termin darf nicht vor dem aktiven Release liegen.")
            if active["version"] == version:
                blockers.append("Eine neue eindeutige Releaseversion vergeben.")
            for source in inputs["outlines"]:
                key = profile_key(source)
                if key in keys:
                    raise Invalid("Zwei Preprod-Fassungen besitzen dasselbe Zielprofil: " + key)
                keys.add(key)
                if source["profile"]["environment"] != "preprod":
                    raise Invalid("Nur Preprod-Gliederungen in ein Releasepaket aufnehmen.")
                if source["metadata"]["status"] != "Freigegeben":
                    blockers.append(source["title"] + ": Preprod-Stand ist nicht freigegeben.")
                if not source["profile"]["market"].strip():
                    blockers.append(source["title"] + ": Markt muss ausdrücklich angegeben sein.")
                prior = self._outline(previous[key]["outline_id"], db) if key in previous else None
                if prior and prior["revision"] != previous[key]["revision"]:
                    blockers.append(source["title"] + ": Aktiver Prod-Stand wurde außerhalb der Releaseverwaltung verändert.")
                candidate = copy.deepcopy(source)
                candidate["id"] = prior["id"] if prior else uid()
                candidate["revision"] = prior["revision"] if prior else 0
                candidate["title"] = prior["title"] if prior else source["title"] + " · Prod"
                candidate["metadata"].update(version=version, status="Entwurf")
                candidate["profile"].update(environment="prod", release=version, as_of=at)
                candidate = validate_outline(self.store.media.resolve(self.store.library.resolve(candidate)))
                plan = compose(candidate, candidate["profile"])
                errors = editorial.release_errors(plan)
                blockers.extend(source["title"] + ": " + error for error in errors)
                excluded = [{"chapter": c["title"], "reason": e["reason"]} for c in plan["chapters"] for e in c["excluded"]]
                invisible = [c["title"] for c in plan["chapters"] if not c["visible"]]
                if excluded or invisible:
                    warnings.append(source["title"] + ": Im Prod-Profil entfallen Kapitel/Texte. Details vor Aktivierung prüfen.")
                assignments = [{"chunk_id": cid, "chapter_id": chid} for cid, chid in db.execute("SELECT chunk_id,chapter_id FROM assignments WHERE outline_id=? ORDER BY chunk_id,chapter_id", (source["id"],))]
                old_links = [{"chunk_id": cid, "chapter_id": chid} for cid, chid in db.execute("SELECT chunk_id,chapter_id FROM assignments WHERE outline_id=? ORDER BY chunk_id,chapter_id", (prior["id"],))] if prior else []
                members.append({"key": key, "source_id": source["id"], "source_revision": source["revision"], "source_title": source["title"],
                                "candidate": candidate, "before": prior, "before_links": old_links, "assignments": assignments,
                                "excluded": excluded, "invisible": invisible, "visible_chapters": sum(c["visible"] for c in plan["chapters"]),
                                "text_count": sum(len(c["blocks"]) for c in plan["chapters"] if c["visible"]),
                                "comparison": compare_outlines(prior, candidate) if prior else None})
            missing = sorted(set(previous) - keys)
            blockers.extend("Bisheriges Prod-Profil fehlt im Paket: " + key for key in missing)
            for conflict in self.store.review.blockers(ids, db):
                blockers.append("Quellenprüfung offen: " + conflict["left"]["name"] + " ↔ " + conflict["right"]["name"] + " (" + conflict["effective_status"] + ")")
            if not inputs["chunks"]:
                warnings.append("Keine bestätigten Chunk-Zuordnungen: Quellenwidersprüche können für dieses Paket nicht vollständig zugeordnet werden.")
            if not active["members"]:
                warnings.append("Erste Prod-Baseline: Alle benötigten Markt-/Rollen-/Spartenprofile ausdrücklich aufnehmen. Bereits vorhandene Gliederungen werden nicht automatisch als aktive Prod-Baseline übernommen.")
            package = {"id": old["id"] if old else uid(), "revision": old["revision"]+1 if old else 1, "version": version, "date": at,
                       "created": old["created"] if old else now(), "updated": now(), "status": "In Prüfung", "sources": ids,
                       "fingerprint": digest(inputs), "previous_active": active, "members": members,
                       "blockers": list(dict.fromkeys(blockers)), "warnings": warnings, "note": ""}
            db.execute("INSERT INTO release_packages VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,payload=excluded.payload", (package["id"], package["revision"], json.dumps(package, ensure_ascii=False)))
            self._event(package, "Vorschau erstellt", "Prod-Stand unverändert.", db)
            return package

    def promote(self, data):
        from app import Invalid, Conflict, clean_text, now
        note = clean_text(data.get("note", ""), "Freigabebegründung", 5000).strip()
        if data.get("acknowledged") is not True or not note:
            raise Invalid("Änderungen, Quellenlage und Profilabdeckung prüfen, bestätigen und begründen.")
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            package = self.get(data.get("id"), db)
            if package["status"] != "In Prüfung" or type(data.get("revision")) is not int or package["revision"] != data["revision"]:
                raise Conflict("Releasepaket geändert oder bereits aktiviert.")
            if package["fingerprint"] != digest(self._inputs(package["sources"], db)):
                raise Conflict("Ausgangsstände, Prod, Quellenprüfung oder Taxonomie verändert. Vorschau erneut erstellen.")
            if package["blockers"]:
                raise Invalid("Promotion blockiert: " + " | ".join(package["blockers"]))
            if package["date"] > date.today().isoformat():
                raise Invalid("Der geplante Prod-Termin liegt noch in der Zukunft. Zum Termin manuell aktivieren.")
            production = {"revision": package["previous_active"]["revision"]+1, "package_id": package["id"], "version": package["version"], "date": package["date"], "members": []}
            for member in package["members"]:
                saved = self.store.save(member["candidate"], releasing=True, connection=db)
                db.execute("DELETE FROM assignments WHERE outline_id=?", (saved["id"],))
                db.executemany("INSERT INTO assignments VALUES(?,?,?)", [(link["chunk_id"], saved["id"], link["chapter_id"]) for link in member["assignments"]])
                production["members"].append({"key": member["key"], "outline_id": saved["id"], "revision": saved["revision"]})
                member["promoted_revision"] = saved["revision"]
            package.update(status="Aktiviert", revision=package["revision"]+1, updated=now(), note=note)
            db.execute("UPDATE production_state SET payload=? WHERE singleton=1", (json.dumps(production, ensure_ascii=False),))
            db.execute("UPDATE release_packages SET revision=?,payload=? WHERE id=?", (package["revision"], json.dumps(package, ensure_ascii=False), package["id"]))
            self._event(package, "Nach Prod übernommen", note, db)
            return package

    def rollback(self, data):
        from app import Invalid, Conflict, clean_text, now
        note = clean_text(data.get("note", ""), "Rücknahmegrund", 5000).strip()
        if not note or data.get("acknowledged") is not True:
            raise Invalid("Rücknahme bestätigen und begründen.")
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            package = self.get(data.get("id"), db)
            active = self.active(db)
            if active["package_id"] != package["id"] or package["status"] != "Aktiviert" or data.get("revision") != package["revision"]:
                raise Conflict("Nur das aktuell aktive Releasepaket kann zurückgenommen werden.")
            restored = copy.deepcopy(package["previous_active"])
            restored["revision"] = active["revision"] + 1
            revisions = {}
            for member in package["members"]:
                current = self._outline(member["candidate"]["id"], db)
                expected = next(m["revision"] for m in active["members"] if m["outline_id"] == current["id"])
                if current["revision"] != expected:
                    raise Conflict("Prod wurde nach Promotion geändert. Rücknahme würde Änderungen überschreiben; zuerst fachlich klären.")
                links = [{"chunk_id":cid,"chapter_id":chid} for cid,chid in db.execute("SELECT chunk_id,chapter_id FROM assignments WHERE outline_id=? ORDER BY chunk_id,chapter_id", (current["id"],))]
                if links != member["assignments"]:
                    raise Conflict("Prod-Quellenzuordnungen wurden nach Promotion geändert. Rücknahme würde Änderungen überschreiben; zuerst fachlich klären.")
                prior = copy.deepcopy(member["before"])
                candidate = prior or current
                candidate["revision"] = current["revision"]
                if not prior:
                    candidate["metadata"]["status"] = "Archiviert"
                saved = self.store.save(candidate, releasing=bool(prior and prior["metadata"]["status"] == "Freigegeben"), connection=db)
                revisions[saved["id"]] = saved["revision"]
                db.execute("DELETE FROM assignments WHERE outline_id=?", (saved["id"],))
                for link in member["before_links"]:
                    if not db.execute("SELECT 1 FROM chunks WHERE id=?", (link["chunk_id"],)).fetchone():
                        raise Conflict("Eine frühere Quellenzuordnung fehlt. Rücknahme vollständig abgebrochen.")
                    db.execute("INSERT INTO assignments VALUES(?,?,?)", (link["chunk_id"], saved["id"], link["chapter_id"]))
            for member in restored["members"]:
                member["revision"] = revisions[member["outline_id"]]
            package.update(status="Zurückgenommen", revision=package["revision"]+1, updated=now())
            db.execute("UPDATE production_state SET payload=? WHERE singleton=1", (json.dumps(restored, ensure_ascii=False),))
            db.execute("UPDATE release_packages SET revision=?,payload=? WHERE id=?", (package["revision"], json.dumps(package, ensure_ascii=False), package["id"]))
            self._event(package, "Zurückgenommen", note, db)
            return package
