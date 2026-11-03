"""Durable, reviewable local agent pipelines. Agent steps never publish documents."""
import copy
import json
import re

import sources
import language_workflow

AGENTS = {"triage": "Wissensagent", "structure": "Gliederungsagent", "media": "Bildagent", "quality": "Qualitätsagent", "translation": "Übersetzungsagent",
          "finalization": "Finalisierung", "validation": "Validierung", "layout": "Layout", "documentation": "Dokumentation"}


class Orchestrator:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS agent_jobs(id TEXT PRIMARY KEY,payload TEXT)")
            for jid, payload in db.execute("SELECT id,payload FROM agent_jobs").fetchall():
                row = json.loads(payload)
                if row["status"] == "running":
                    row["status"] = "paused"; row["error"] = "Anwendung neu gestartet. Letzten Schritt ausdrücklich fortsetzen."
                    db.execute("UPDATE agent_jobs SET payload=? WHERE id=?", (json.dumps(row,ensure_ascii=False),jid))

    def get(self, jid, db=None):
        from app import Invalid
        if db is None:
            with self.store.connect() as conn: return self.get(jid,conn)
        row = db.execute("SELECT payload FROM agent_jobs WHERE id=?", (jid,)).fetchone()
        if not row: raise Invalid("Agentenlauf nicht gefunden.")
        return json.loads(row[0])

    def listing(self):
        with self.store.connect() as db:
            return [{k:r[k] for k in ["id","title","status","created","index","steps","mode"]} for (raw,) in db.execute("SELECT payload FROM agent_jobs ORDER BY rowid DESC") for r in [json.loads(raw)]]

    def start(self, data):
        from app import Invalid, choice, clean_text, uid, now, LANGUAGES
        outline = self.store.get(clean_text(data.get("outline_id"), "Gliederung", 100))
        selected = data.get("sources", [])
        agents = data.get("agents", ["triage","structure","media","quality"])
        if not isinstance(selected,list) or len(selected) > 20: raise Invalid("Höchstens 20 Quellen wählen.")
        if not isinstance(agents,list) or not agents or any(a not in AGENTS for a in agents): raise Invalid("Agenten auswählen.")
        mode = choice(data.get("mode","rules"),["rules","ollama"],"Verarbeitung")
        model = clean_text(data.get("model", ""), "Modell", 150)
        if ((mode=="ollama" and "triage" in agents) or "translation" in agents) and not model.strip(): raise Invalid("Für KI-Schritte ein installiertes lokales Modell angeben.")
        chunks = []
        for sid in dict.fromkeys(selected):
            for chunk in self.store.sources.chunks(sid):
                chunks.append({"id":chunk["id"],"source_id":sid,"revision":chunk["revision"],"text":chunk["text"],"location":chunk["location"]})
        if len(chunks)>200 or (not chunks and any(a in agents for a in ["triage","structure","translation"])): raise Invalid("Wissens-/Gliederungs-/Übersetzungsagent benötigen 1–200 Chunks. Quellen wählen oder aufteilen.")
        steps=[]
        for agent in ["triage", "structure", "media", "translation", "quality", "finalization", "validation", "layout", "documentation"]:
            if agent in agents:
                steps.extend({"agent":agent,"chunk":i,"status":"pending"} for i in range(len(chunks))) if agent in ["triage","translation"] else steps.append({"agent":agent,"status":"pending"})
        taxonomy=self.store.taxonomy()
        row={"id":uid(),"title":outline["title"],"created":now(),"status":"queued","mode":mode,"model":model,"index":0,"steps":steps,
             "outline":outline,"taxonomy":taxonomy,"targets":self.store.get_catalog(),"chunks":chunks,"candidates":[],"reports":[],"error":"",
             "source_language":choice(data.get("source_language","de"),LANGUAGES,"Ausgangssprache"),"target_language":choice(data.get("target_language","en"),LANGUAGES,"Zielsprache")}
        for chunk in (chunks if any(a in agents for a in ["triage", "structure", "translation"]) else []):
            row["candidates"].append({"id":chunk["id"],"text":chunk["text"],"labels":{},"language":row["source_language"],"location":chunk["location"]})
        with self.store.connect() as db: db.execute("INSERT INTO agent_jobs VALUES(?,?)",(row["id"],json.dumps(row,ensure_ascii=False)))
        return row

    def step(self, jid):
        from app import Conflict
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE"); row=self.get(jid,db)
            if row["status"]=="running": raise Conflict("Dieser Schritt läuft bereits.")
            if row["status"] in ["review","completed","cancelled"]: return row
            row["status"]="running";row["error"]=""
            db.execute("UPDATE agent_jobs SET payload=? WHERE id=?",(json.dumps(row,ensure_ascii=False),jid))
        try:
            step=row["steps"][row["index"]];agent=step["agent"]
            if agent=="triage":
                i=step["chunk"];chunk=row["chunks"][i]
                labels=sources.ollama_suggestion(chunk,row["outline"],row["targets"],row["model"]) if row["mode"]=="ollama" else sources.rules(chunk,row["outline"],row["targets"])
                row["candidates"][i]["labels"]=labels
            elif agent=="structure":
                for i, candidate in enumerate(row["candidates"]):
                    if not candidate["labels"]: candidate["labels"]=sources.rules(row["chunks"][i],row["outline"],row["targets"])
                row["reports"].append({"agent":agent,"text":"Kapitelvorschläge anhand des gespeicherten Gliederungsstands erstellt; keine Kapitel automatisch geändert."})
            elif agent=="media":
                from app import compose
                plan=compose(row["outline"],row["outline"]["profile"])
                warnings=[w for w in plan["warnings"] if any(k in w for k in ["Bild", "Klickstrecke", "Schritt"])]
                row["reports"].append({"agent":agent,"text":"Medienprüfung: "+(" | ".join(warnings) or "Keine fehlenden Medienanforderungen im gespeicherten Ausgabeprofil erkannt.")})
            elif agent=="quality":
                from collections import Counter
                from app import compose
                counts=Counter(c["text"].strip().casefold() for c in row["chunks"])
                duplicates=sum(n-1 for n in counts.values() if n>1)
                plan=compose(row["outline"],row["outline"]["profile"])
                row["reports"].append({"agent":agent,"text":f"{duplicates} doppelte Text-Chunks. {len(plan['warnings'])} Ausgabeprüfpunkte. Automatische Klassifikation ersetzt keine fachliche Prüfung.","warnings":plan["warnings"]})
            elif agent=="translation":
                i=step["chunk"];chunk=row["chunks"][i]
                entry={"id":chunk["id"],"revision":chunk["revision"],"title":chunk["location"],"block":{"text":chunk["text"],"language":row["source_language"]}}
                proposal=language_workflow.generate(entry,"translate",row["target_language"],row["model"])
                row["candidates"][i].update(text=proposal["text"],language=row["target_language"],translation_proposal=proposal)
            elif agent=="finalization":
                from publication import matrix
                from app import compose
                from editorial import release_errors
                result=matrix(row["outline"])
                counts={kind:sum(r["uses"][kind]["included"] for r in result["rows"]) for kind in result["warnings"]}
                issues=release_errors(compose(row["outline"],row["outline"]["profile"]))
                row["reports"].append({"agent":agent,"text":f"Freigabebereitschaft: {len(issues)} Prüfpunkte. Verwendbare Texte: "+", ".join(f"{k}: {n}" for k,n in counts.items()),"warnings":issues})
            elif agent=="validation":
                from app import validate_outline, compose
                from editorial import release_errors
                validated=validate_outline(row["outline"])
                plan=compose(validated,validated["profile"])
                issues=release_errors(plan)
                row["reports"].append({"agent":agent,"text":f"Struktur und Felder sind formal gültig. {len(issues)} fachliche/regelbasierte Prüfpunkte bleiben. Interne Jira-Nachweise sind vom Leserinhalt getrennt.","warnings":issues})
            elif agent=="layout":
                from app import compose, office_export
                import renderers
                plan=compose(row["outline"],row["outline"]["profile"])
                loader=lambda aid,rev:self.store.media.image(aid,rev,"intern")
                sizes={}
                for fmt in ["docx","pptx","html","pdf"]:
                    ref=row["outline"].get("layout",{}).get(fmt)
                    template=self.store.layouts.snapshot(ref,fmt)[1] if ref else None
                    artifact=renderers.html_export(plan,loader) if fmt=="html" else renderers.pdf_export(plan,loader) if fmt=="pdf" else office_export(plan,fmt,loader,template)
                    sizes[fmt]=len(artifact)
                row["reports"].append({"agent":agent,"text":"Technische Renderprobe erfolgreich: "+", ".join(f"{fmt.upper()} {size} Bytes" for fmt,size in sizes.items())+". Sichtprüfung in Microsoft Office und mit euren Templates bleibt erforderlich. Keine Veröffentlichung erfolgt.","sizes":sizes})
            elif agent=="documentation":
                from version import VERSION, RELEASE_DATE
                outline=row["outline"];p=outline["profile"]
                report=f"# Interner Finalisierungsbericht\n\noneSCM-360 {VERSION} · {RELEASE_DATE}\n\nGliederung: {outline['title']}\n\nVersion {outline['metadata']['version']} · Revision {outline['revision']} · Status {outline['metadata']['status']}\n\nProfil: {p['role']} / {p['market'] or 'Land offen'} / {p['division']} / {p['language']} / {p['scope']}\n\nStichtag: {p.get('as_of') or 'offen'} · Umgebung: {p.get('environment','prod')} · Release: {p['release'] or 'offen'}\n\n"
                for result in row["reports"]:
                    report+=f"## {AGENTS[result['agent']]}\n\n{result['text']}\n\n"
                    for warning in result.get("warnings",[]): report+="- "+warning+"\n"
                    report+="\n"
                report+="## Grenzen\n\nDies ist ein interner Prüfbericht, keine Freigabe. Modellqualität und visuelle Darstellung in der Zielumgebung müssen fachlich geprüft werden. Der Lauf verändert keine freigegebenen Dokumente.\n"
                row["report_markdown"]=report
                row["reports"].append({"agent":agent,"text":"Interner Markdown-Bericht mit Ausgangsstand, Profil, Ergebnissen und offenen Prüfpunkten erstellt."})
            step["status"]="done";row["index"]+=1
            row["status"]=("review" if row["candidates"] else "completed") if row["index"]==len(row["steps"]) else "queued"
        except Exception as exc:
            row["status"]="failed";row["error"]=str(exc)[:1000]
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current=self.get(jid,db)
            if current["status"]=="cancelled": return current
            db.execute("UPDATE agent_jobs SET payload=? WHERE id=?",(json.dumps(row,ensure_ascii=False),jid))
        return row

    def cancel(self,jid):
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE");row=self.get(jid,db)
            if row["status"] not in ["review","completed"]: row["status"]="cancelled"
            db.execute("UPDATE agent_jobs SET payload=? WHERE id=?",(json.dumps(row,ensure_ascii=False),jid))
        return row

    def apply(self,data):
        from app import Invalid, Conflict, uid, now, block
        from publication import validate_evidence
        selected=data.get("selected",[])
        if not isinstance(selected,list) or not selected: raise Invalid("Mindestens einen geprüften Vorschlag auswählen.")
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE");row=self.get(data.get("id"),db)
            if row["status"]!="review": raise Conflict("Lauf steht nicht zur Übernahme bereit.")
            live=db.execute("SELECT revision FROM outlines WHERE id=?",(row["outline"]["id"],)).fetchone()
            taxonomy=db.execute("SELECT revision FROM taxonomy WHERE singleton=1").fetchone()[0]
            if not live or live[0]!=row["outline"]["revision"] or taxonomy!=row["taxonomy"]["revision"]:
                raise Conflict("Gliederung oder Domänen haben sich geändert. Neuen Lauf starten; alte Ergebnisse bleiben sichtbar.")
            candidates={c["id"]:c for c in row["candidates"]};chunks={c["id"]:c for c in row["chunks"]}
            if any(cid not in candidates for cid in selected): raise Invalid("Ungültige Vorschlagsauswahl.")
            for cid in set(selected):
                live=db.execute("SELECT revision FROM chunks WHERE id=?",(cid,)).fetchone()
                if not live or live[0]!=chunks[cid]["revision"]: raise Conflict("Quellchunk wurde gelöscht oder geändert. Neuen Lauf starten.")
            new_blocks=[]
            for cid in set(selected):
                candidate=candidates[cid]
                labels=sources.validate_labels(candidate["labels"],{d["id"] for d in row["targets"]})
                db.execute("UPDATE chunks SET labels=?, revision=revision+1 WHERE id=?",(json.dumps(labels,ensure_ascii=False),cid))
                valid_chapters={c["id"] for c in row["outline"]["chapters"]}
                for chapter_id in candidate["labels"].get("chapter_ids",[]):
                    if chapter_id in valid_chapters: db.execute("INSERT OR IGNORE INTO assignments VALUES(?,?,?)",(cid,row["outline"]["id"],chapter_id))
                if data.get("create_drafts") is True:
                    b=block();b.update(text=candidate["text"],language=candidate["language"],source=f"Quellchunk {cid}",note=f"Agentenlauf {row['id']} · Quellrevision {chunks[cid]['revision']}")
                    keys=list(dict.fromkeys(re.findall(r"\b[A-Z][A-Z0-9_]+-\d+\b",chunks[cid]["text"])))[:50]
                    b["assignment"]={"conditions":{"role":labels["roles"]},"note":""}
                    b["evidence"]=validate_evidence([{"key":key,"verified":False} for key in keys])
                    item={"id":uid(),"revision":1,"title":candidate["labels"].get("topic") or candidate["location"],"block":b,
                          "domains":labels["domain_ids"],"tags":", ".join(labels["keywords"]),"archived":False,"mandatory_term":False,"updated":now(),
                          "agent_provenance":{"job_id":row["id"],"chunk_id":cid,"chunk_revision":chunks[cid]["revision"],"translation":candidate.get("translation_proposal")}}
                    raw=json.dumps(item,ensure_ascii=False)
                    db.execute("INSERT INTO library VALUES(?,?,?)",(item["id"],1,raw));db.execute("INSERT INTO library_history VALUES(?,?,?)",(item["id"],1,raw));new_blocks.append(item["id"])
            row["status"]="completed";row["applied"]=list(dict.fromkeys(selected));row["created_blocks"]=new_blocks
            db.execute("UPDATE agent_jobs SET payload=? WHERE id=?",(json.dumps(row,ensure_ascii=False),row["id"]))
        return row
