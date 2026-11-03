"""Separate editorial-only knowledge register. Never a document content provider."""
import json

DEFAULT_CATEGORIES = [
    {"id":"internal-testing","name":"Testing","parent_id":""},
    {"id":"internal-ui","name":"UI","parent_id":""},
    {"id":"internal-control","name":"Steuerung","parent_id":""},
    {"id":"internal-it","name":"IT-Themen","parent_id":""},
]


class InternalKnowledge:
    def __init__(self, store):
        self.store=store
        with store.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS internal_categories(singleton INTEGER PRIMARY KEY CHECK(singleton=1),revision INTEGER,payload TEXT);
                CREATE TABLE IF NOT EXISTS internal_entries(id TEXT PRIMARY KEY,revision INTEGER,payload TEXT);
                CREATE TABLE IF NOT EXISTS internal_history(id TEXT,revision INTEGER,payload TEXT,PRIMARY KEY(id,revision));
            """)
            db.execute("INSERT OR IGNORE INTO internal_categories VALUES(1,0,?)",(json.dumps(DEFAULT_CATEGORIES,ensure_ascii=False),))

    def categories(self):
        with self.store.connect() as db:
            revision,payload=db.execute("SELECT revision,payload FROM internal_categories WHERE singleton=1").fetchone()
        return {"revision":revision,"items":json.loads(payload)}

    def save_categories(self,data):
        from app import Invalid, Conflict, clean_text
        rows=data.get("items")
        if not isinstance(rows,list) or not 4<=len(rows)<=200: raise Invalid("4–200 interne Themen verwenden.")
        cleaned=[];seen=set()
        for row in rows:
            item={"id":clean_text(row.get("id"),"Themen-ID",100),"name":clean_text(row.get("name"),"Themenname",150).strip(),"parent_id":clean_text(row.get("parent_id",""),"Oberthema",100)}
            if not item["id"] or item["id"] in seen or not item["name"]: raise Invalid("Themenname oder eindeutige Kennung fehlt.")
            seen.add(item["id"]);cleaned.append(item)
        by_id={r["id"]:r for r in cleaned}
        for item in cleaned:
            node=item;parents={item["id"]}
            while node["parent_id"]:
                if node["parent_id"] not in by_id or node["parent_id"] in parents or len(parents)>=4: raise Invalid("Interne Themen dürfen keine Zyklen bilden und maximal vier Ebenen haben.")
                parents.add(node["parent_id"]);node=by_id[node["parent_id"]]
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            revision,payload=db.execute("SELECT revision,payload FROM internal_categories WHERE singleton=1").fetchone()
            if type(data.get("revision")) is not int or revision!=data["revision"]: raise Conflict("Themen wurden geändert. Register neu öffnen.")
            if {r["id"] for r in json.loads(payload)}-seen: raise Invalid("Bestehende interne Themen erhalten; Umbenennen und Ergänzen sind möglich.")
            db.execute("UPDATE internal_categories SET revision=?,payload=? WHERE singleton=1",(revision+1,json.dumps(cleaned,ensure_ascii=False)))
        return {"revision":revision+1,"items":cleaned}

    def listing(self):
        with self.store.connect() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT payload FROM internal_entries ORDER BY rowid DESC")]

    def save(self,data):
        from app import Invalid, Conflict, clean_text, choice, boolean, ROLES, LANGUAGES, now
        from publication import validate_evidence
        if type(data.get("revision")) is not int or data["revision"]<0: raise Invalid("Interne Revision fehlt.")
        item={"id":clean_text(data.get("id"),"ID",100),"revision":data["revision"]+1,
              "title":clean_text(data.get("title"),"Titel",300).strip(),"body":clean_text(data.get("body",""),"Interner Inhalt",100000),
              "question":clean_text(data.get("question",""),"FAQ-Frage",2000),"answer":clean_text(data.get("answer",""),"FAQ-Antwort",30000),
              "source":clean_text(data.get("source",""),"Quelle",2000),"note":clean_text(data.get("note",""),"Vermerk",5000),
              "status":choice(data.get("status","Entwurf"),["Entwurf","In Prüfung","Freigegeben","Archiviert"],"Status"),
              "language":choice(data.get("language","de"),LANGUAGES,"Sprache"),
              "chatbot_enabled":boolean(data.get("chatbot_enabled",False),"Chatbot-Vormerkung"),
              "evidence":validate_evidence(data.get("evidence",[])),"visibility":"internal_only","updated":now()}
        if not item["id"] or not item["title"]: raise Invalid("Interner Titel und ID erforderlich.")
        for key in ["categories","domains","roles","markets","labels","keywords"]:
            values=data.get(key,[])
            if not isinstance(values,list) or len(values)>200 or any(not isinstance(v,str) or len(v)>150 for v in values): raise Invalid("Ungültige interne Labels: "+key)
            item[key]=list(dict.fromkeys(v.strip() for v in values if v.strip()))
        valid_categories={c["id"] for c in self.categories()["items"]}
        if not item["categories"] or set(item["categories"])-valid_categories: raise Invalid("Mindestens ein gültiges internes Thema auswählen.")
        if set(item["domains"])-{d["id"] for d in self.store.get_catalog()} or set(item["roles"])-set(ROLES): raise Invalid("Ungültige Domänen-/Rollenreferenz.")
        if item["chatbot_enabled"] and (not item["question"].strip() or not item["answer"].strip()): raise Invalid("Für die Chatbot-Vormerkung Frage und Antwort ergänzen.")
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old=db.execute("SELECT revision,payload FROM internal_entries WHERE id=?",(item["id"],)).fetchone()
            if (old and old[0]!=data["revision"]) or (not old and data["revision"]): raise Conflict("Interner Eintrag wurde geändert. Register neu öffnen.")
            item["created"]=json.loads(old[1])["created"] if old else item["updated"]
            payload=json.dumps(item,ensure_ascii=False)
            db.execute("INSERT INTO internal_entries VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,payload=excluded.payload",(item["id"],item["revision"],payload))
            db.execute("INSERT INTO internal_history VALUES(?,?,?)",(item["id"],item["revision"],payload))
        return item

    def history(self,entry_id):
        with self.store.connect() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT payload FROM internal_history WHERE id=? ORDER BY revision DESC",(entry_id,))]

    def chatbot_preview(self,data):
        """Internal retrieval preview only: no model, external call, or reader export."""
        from app import clean_text
        query=clean_text(data.get("query",""),"Suchfrage",2000).casefold()
        words=set(query.split());rows=[]
        for entry in self.listing():
            if entry["status"]!="Freigegeben" or not entry["chatbot_enabled"]: continue
            if data.get("language") and entry["language"]!=data["language"]: continue
            if data.get("role") and entry["roles"] and data["role"] not in entry["roles"]: continue
            if data.get("market") and entry["markets"] and data["market"] not in entry["markets"]: continue
            hay=" ".join([entry["question"],entry["answer"],entry["title"],*entry["keywords"],*entry["labels"]]).casefold()
            score=sum(w in hay for w in words)
            if words and not score: continue
            rows.append({"id":entry["id"],"revision":entry["revision"],"question":entry["question"],"answer":entry["answer"],"source":entry["source"],"categories":entry["categories"],"score":score,"visibility":"internal_only"})
        return sorted(rows,key=lambda r:-r["score"])[:30]
