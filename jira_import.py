"""Ticket-preserving Jira HTML imports. Only scrubbed, inert HTML reaches storage."""
import copy
import hashlib
import html as escape_html
import json
import re
from urllib.parse import urlparse, parse_qs

from lxml import etree, html

KEY = re.compile(r"\b[A-Z][A-Z0-9_]+-\d+\b")
PERSON_FIELDS = {"assignee", "reporter", "creator", "watchers", "watches", "worklog", "lastviewed"}
PERSON_LABEL = re.compile(r"^(?:bearbeiter|erfasser|ersteller|autor|melder|verantwortlicher|assignee|reporter|creator|author|watchers|beobachter|benutzer|user|account|kommentarautor|comment author)(?:\b|[ :])", re.I)
PERSON_CLASS = re.compile(r"(?:^|[\s_-])(?:author|user-hover|user-avatar|avatar|commentauthor|comment-author|userprofile-link)(?:$|[\s_-])", re.I)
ALLOWED = {"p", "div", "span", "br", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "pre", "code", "strong", "b", "em", "i", "table", "tbody", "thead", "tr", "td", "th", "blockquote", "time"}
DROP = {"script", "style", "iframe", "object", "embed", "svg", "img", "input", "button", "select", "textarea", "noscript", "template"}


def checked_html(value, fragment=False):
    """HTML recovery must never turn a resource-limited partial tree into an import."""
    parser = html.HTMLParser(no_network=True, remove_comments=True)
    try:
        root = (html.fragment_fromstring(value, create_parent=True, parser=parser)
                if fragment else html.fromstring(value, parser=parser))
    except (etree.ParserError, etree.XMLSyntaxError) as exc:
        raise ValueError("HTML konnte nicht vollständig gelesen werden. Export prüfen oder in kleinere Dateien aufteilen.") from exc
    # lxml's HTML recovery can return a tree after dropping a large text node or
    # the rest of the document. Check the log even when no exception was raised.
    if any(error.level_name == "FATAL" or error.type_name == "ERR_RESOURCE_LIMIT"
           for error in parser.error_log):
        raise ValueError("HTML überschreitet eine Parsergrenze und wurde nicht importiert. Export vereinfachen oder in kleinere Dateien aufteilen.")
    return root


def text_of(node):
    return " ".join("".join(node.itertext()).split()).strip()


class Scrubber:
    def __init__(self, root, labels):
        self.identities = set()
        self.fields = 0
        self.replacements = 0
        for node in root.iter():
            if not isinstance(node.tag, str):
                continue
            classes = node.get("class", "").split()
            field = next((c for c in classes if c in labels or c.lower() in PERSON_FIELDS), "")
            if field.lower() in PERSON_FIELDS or field and PERSON_LABEL.search(labels.get(field, "")):
                self.fields += 1
                self.identity(text_of(node))
            if node.tag == "tr":
                cells = node.xpath('./td|./th')
                if len(cells) > 1 and PERSON_LABEL.search(text_of(cells[0])):
                    self.fields += 1
                    for cell in cells[1:]:self.identity(text_of(cell))
            if node.tag in {"p", "div", "span"} and len(node) == 0:
                match = re.match(r"(?i)^(?:Bearbeiter|Erfasser|Ersteller|Autor|Assignee|Reporter|Creator|Comment author|Kommentarautor)\s*:\s*(.+)$", text_of(node))
                if match:self.identity(match.group(1))
            if self.person_node(node):
                self.identity(text_of(node))
            for attr in ["data-username", "data-displayname", "data-display-name", "data-user", "data-author"]:
                if node.get(attr):
                    self.identity(node.get(attr))
            if node.tag == "a":
                href = node.get("href", "")
                if re.search(r"(?:ViewProfile|/people/|/users?/|accountId=|username=|userName=|/secure/useravatar)", href, re.I):
                    self.identity(text_of(node))
                    for key, values in parse_qs(urlparse(href).query).items():
                        if key.casefold() in {"name", "username", "accountid"}:
                            for value in values:self.identity(value)
            # Jira Word exports often encode comment authors in a header line.
            if "comment" in node.get("class", "").casefold() and "header" in node.get("class", "").casefold():
                value = text_of(node)
                match = re.search(r"(?:Comment by|Kommentar von|Added by|Hinzugefügt von)\s+(.+?)(?:\s*\[|\s+(?:am|on|at)\s+\d|$)", value, re.I)
                if match:self.identity(match.group(1))
        values = sorted(self.identities, key=len, reverse=True)
        self.names = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(v) for v in values) + r")(?!\w)", re.I) if values else None

    def identity(self, value):
        value = " ".join(value.split()).strip()
        if 2 <= len(value) <= 160 and value.casefold() not in {"unassigned", "nicht zugewiesen", "anonymous", "anonym", "none", "keine", "user", "account", "system", "unknown", "unbekannt", "automatic", "automatisch"}:
            self.identities.add(value)
            # Also redact the display name without Jira's appended account suffix.
            plain = re.sub(r"\s*[\[(].*?[\])]\s*$", "", value).strip()
            if len(plain.split()) >= 2:self.identities.add(plain)

    @staticmethod
    def person_node(node):
        if PERSON_CLASS.search(node.get("class", "")):
            return True
        return node.tag == "a" and bool(re.search(r"(?:ViewProfile|/people/|/users?/|accountId=|username=|userName=)", node.get("href", ""), re.I))

    def clean(self, value):
        value = value or ""
        if self.names:
            value, count = self.names.subn("[Person entfernt]", value)
            self.replacements += count
        patterns = [
            (r"(?i)\b[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[E-Mail entfernt]"),
            (r"(?i)\b[A-Z]{2}\s?\d{2}(?:\s?[A-Z0-9]){11,30}\b", "[IBAN entfernt]"),
            (r"(?i)\b(?:USERID|LOGIN|BENUTZERNAME|USERNAME|FIN|VIN|KENNZEICHEN)\s*[:=]\s*[^\s,;<]+", "[Personenkennung entfernt]"),
            (r"(?<!\w)\+\d[\d ()/.-]{7,}\d(?!\w)", "[Telefon entfernt]"),
            (r"\[~[^\]\n]+\]", "[Person entfernt]"),
        ]
        for pattern, replacement in patterns:
            value, count = re.subn(pattern, replacement, value)
            self.replacements += count
        return value.replace("\x00", "")

    def markup(self, node, depth=0):
        if depth > 80:
            raise ValueError("HTML ist zu tief verschachtelt. Jira-Export vereinfachen.")
        if not isinstance(node.tag, str) or node.tag.lower() in DROP:
            return ""
        if node.get("hidden") is not None or node.get("aria-hidden") == "true" or re.search(r"(?:display\s*:\s*none|visibility\s*:\s*hidden)", node.get("style", ""), re.I):
            return ""
        if node.tag == "tr":
            cells = node.xpath('./td|./th')
            if cells and PERSON_LABEL.search(text_of(cells[0])):
                return ""
        if self.person_node(node):
            self.replacements += 1
            return "[Person entfernt]"
        tag = node.tag.lower()
        content = escape_html.escape(self.clean(node.text))
        for child in node:
            content += self.markup(child, depth+1) + escape_html.escape(self.clean(child.tail))
        if tag == "br":return "<br>"
        if tag not in ALLOWED:return content
        return f"<{tag}>{content}</{tag}>"


def prepare(raw, force=False):
    """Sanitize first; discard original HTML attributes, embedded data and scripts."""
    if not raw.lstrip().startswith(b"<"):
        return None
    root = checked_html(raw)
    headers = root.xpath('//th')
    labels = {}
    for h in headers:
        field = h.get("data-id") or next((c[len("headerrow-"):] for c in h.get("class", "").split() if c.startswith("headerrow-")), "")
        if field:labels[field] = text_of(h)
    rows = root.xpath('//tr[contains(concat(" ",normalize-space(@class)," ")," issuerow ") or td[contains(concat(" ",normalize-space(@class)," ")," issuekey ")]]')
    headings = [] if rows else [e for e in root.xpath('//h1|//h2|//h3') if KEY.search(text_of(e))]
    if not rows and not headings and not force:
        return None
    scrub = Scrubber(root, labels)
    parts, keys = [], set()
    for row in rows:
        cells = {c.get("class", "").split()[0]: c for c in row if c.tag == "td" and c.get("class")}
        key_cell = cells.get("issuekey")
        found = KEY.search(text_of(key_cell)) if key_cell is not None else None
        if not found:
            raise ValueError("Eine Jira-Zeile hat keine lesbare Ticketnummer. Import abgebrochen, damit kein Ticket verloren geht.")
        key = found.group()
        if key in keys:raise ValueError("Doppelte Ticketnummer im Export: " + key + ". Eindeutigen Export verwenden.")
        keys.add(key)
        summary = scrub.clean(text_of(cells["summary"])) if "summary" in cells else "Ohne Zusammenfassung"
        title = key + " · " + summary
        fields, body = {}, ["<h1>" + escape_html.escape(title) + "</h1>"]
        for field, cell in cells.items():
            label = labels.get(field, field)
            if field in {"issuekey", "summary", "thumbnail"} or field.lower() in PERSON_FIELDS or PERSON_LABEL.search(label):
                continue
            value = scrub.markup(cell)
            if not text_of(checked_html(value or "<span></span>", fragment=True)):
                continue
            body.extend(["<h2>"+escape_html.escape(scrub.clean(label))+"</h2>", value])
            if field in ["status", "issuetype", "created", "updated", "fixVersions", "versions"]:
                fields[field] = scrub.clean(text_of(cell))
        parts.append({"html": '<article data-jira-key="'+key+'">'+"\n".join(body)+"</article>",
                      "details": {"ticket_key": key, "title": title, "text_format": "markdown", "jira_fields": fields, "pii_processed": True}})
    if headings:
        # Common Jira detail/Word export: heading followed by sibling field tables.
        for heading in headings:
            key = KEY.search(text_of(heading)).group()
            if key in keys:raise ValueError("Doppelte Ticketüberschrift: " + key)
            keys.add(key)
            summary = scrub.clean(text_of(heading))
            siblings = [heading]
            for sibling in heading.itersiblings():
                if sibling in headings or any(h in sibling.iter() for h in headings):break
                siblings.append(sibling)
            body = "".join(scrub.markup(e) for e in siblings)
            # Remove labelled person rows in detail exports, including plain names.
            fragment = checked_html(body, fragment=True)
            for tr in list(fragment.xpath('.//tr')):
                cells = tr.xpath('./td|./th')
                if cells and PERSON_LABEL.search(text_of(cells[0])):tr.getparent().remove(tr)
            body = "".join(etree.tostring(c, encoding="unicode", method="html") for c in fragment)
            parts.append({"html": '<article data-jira-key="'+key+'">'+body+"</article>",
                          "details": {"ticket_key":key,"title":summary,"text_format":"markdown","jira_fields":{},"pii_processed":True}})
    if not parts:
        body = scrub.markup(root)
        parts = [{"html":"<article>"+body+"</article>", "details":{"title":"Jira-HTML ohne erkanntes Ticketlayout","text_format":"markdown","pii_processed":True}}]
    if len(parts) > 10000:
        raise ValueError("Mehr als 10.000 Tickets; Export in kleinere Dateien aufteilen.")
    warnings = [f"Jira-HTML bereinigt: {len(keys)} Tickets erkannt, {scrub.fields} Personenfelder entfernt. Erfasste Personennamen, Profile, E-Mail-Adressen und erkennbare Personenkennungen wurden entfernt; nur bereinigtes HTML wird gespeichert. Unbekannte PII im Freitext zusätzlich prüfen."]
    if not keys:warnings.append("Kein Jira-Ticketlayout erkannt. Der bereinigte HTML-Inhalt wird als ein Dokument-Chunk übernommen; Ticketgrenzen bitte prüfen.")
    return {"parts":parts,"warnings":warnings,"scrubber":scrub}


def ticket_text(markup):
    root = checked_html(markup)
    def walk(e, depth=0):
        if depth > 80:raise ValueError("Ticketinhalt zu tief verschachtelt.")
        tag = e.tag if isinstance(e.tag,str) else ""
        if tag in DROP:return ""
        content = e.text or ""
        for c in e:content += walk(c,depth+1)+(c.tail or "")
        if tag in {"h1","h2","h3","h4","h5","h6"}:return "\n\n"+"#"*int(tag[1])+" "+" ".join(content.split())+"\n\n"
        if tag == "br":return "\n"
        if tag in {"b","strong"}:return "**"+content+"**" if content.strip() else ""
        if tag in {"i","em"}:return "*"+content+"*" if content.strip() else ""
        if tag == "li":return "\n- "+content.strip()+"\n"
        if tag == "pre":return "\n\n```\n"+content+"\n```\n\n"
        if tag in {"p","div","blockquote","tr","table","ul","ol"}:return "\n"+content+"\n"
        if tag in {"td","th"}:return content+" | "
        return content
    text = walk(root).replace("\r", "")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", text).strip()


def document(parts):
    return ('<!doctype html><html><head><meta charset="utf-8"></head><body>'+"\n".join(p["html"] for p in parts)+"</body></html>").encode()


class Imports:
    def __init__(self, sources):
        self.sources = sources
        self.store = sources.store
        with self.store.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS source_import_jobs(id TEXT PRIMARY KEY,payload TEXT);
                CREATE TABLE IF NOT EXISTS source_import_parts(job_id TEXT REFERENCES source_import_jobs(id) ON DELETE CASCADE,ordinal INTEGER,html TEXT,details TEXT,text TEXT,PRIMARY KEY(job_id,ordinal));
                CREATE TABLE IF NOT EXISTS chunk_details(chunk_id TEXT PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,payload TEXT);
            """)

    def _get(self, jid, db):
        from app import Invalid
        row = db.execute("SELECT payload FROM source_import_jobs WHERE id=?", (jid,)).fetchone()
        if not row:raise Invalid("Importlauf nicht gefunden.")
        return json.loads(row[0])

    def listing(self):
        with self.store.connect() as db:
            return [j for (raw,) in db.execute("SELECT payload FROM source_import_jobs ORDER BY rowid DESC") for j in [json.loads(raw)] if j["status"] == "pending"]

    def start(self, name, raw, data):
        from app import uid, now
        from sources import MAX_FILE
        name, data = self.sources.metadata(name, data)
        if not raw or len(raw) > MAX_FILE:raise ValueError("Maximal 20 MB je Quelldatei.")
        parsed = prepare(raw, force=data.get("kind") == "Jira")
        if parsed is None:return {"status":"completed", "result":self.sources.upload(name,raw,data)}
        scrub = parsed["scrubber"]
        name, metadata = self.sources.metadata(scrub.clean(name), {k:scrub.clean(data.get(k,"")) for k in ["kind","origin","release"]})
        canonical = document(parsed["parts"])
        sha = hashlib.sha256(canonical).hexdigest()
        job = {"id":uid(),"revision":1,"created":now(),"name":name,"metadata":metadata,"total":len(parsed["parts"]),"processed":0,
               "status":"pending","warnings":parsed["warnings"],"sha256":sha,"size":len(canonical)}
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT id FROM sources WHERE sha256=?",(sha,)).fetchone()
            if existing:return {"status":"completed","result":{"id":existing[0],"duplicate":True}}
            db.execute("INSERT INTO source_import_jobs VALUES(?,?)",(job["id"],json.dumps(job,ensure_ascii=False)))
            db.executemany("INSERT INTO source_import_parts VALUES(?,?,?,?,NULL)",[(job["id"],i,p["html"],json.dumps(p["details"],ensure_ascii=False)) for i,p in enumerate(parsed["parts"])])
        return job

    def step(self, data):
        from app import Conflict
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            job = self._get(data.get("id"),db)
            if job["status"] != "pending":return job
            if type(data.get("revision")) is not int or data["revision"] != job["revision"]:raise Conflict("Importfortschritt geändert. Lauf neu laden.")
            rows = db.execute("SELECT ordinal,html FROM source_import_parts WHERE job_id=? AND ordinal>=? ORDER BY ordinal LIMIT 25",(job["id"],job["processed"])).fetchall()
            for ordinal,markup in rows:
                db.execute("UPDATE source_import_parts SET text=? WHERE job_id=? AND ordinal=?",(ticket_text(markup),job["id"],ordinal))
            job["processed"] += len(rows)
            job["revision"] += 1
            if job["processed"] == job["total"]:
                parts = [{"html":h,"details":json.loads(d),"text":t} for h,d,t in db.execute("SELECT html,details,text FROM source_import_parts WHERE job_id=? ORDER BY ordinal",(job["id"],))]
                chunks = [{"text":p["text"],"location":p["details"].get("ticket_key","Jira-HTML"),"details":p["details"]} for p in parts]
                job["result"] = self.sources.store_parsed(job["name"],document(parts),job["metadata"],chunks,job["warnings"],connection=db)
                job["status"] = "completed"
                db.execute("DELETE FROM source_import_parts WHERE job_id=?",(job["id"],))
            db.execute("UPDATE source_import_jobs SET payload=? WHERE id=?",(json.dumps(job,ensure_ascii=False),job["id"]))
            return job

    def cancel(self, data):
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            job = self._get(data.get("id"),db)
            if job["status"] == "pending":
                job["status"] = "cancelled";job["revision"] += 1
                db.execute("DELETE FROM source_import_parts WHERE job_id=?",(job["id"],))
                db.execute("UPDATE source_import_jobs SET payload=? WHERE id=?",(json.dumps(job,ensure_ascii=False),job["id"]))
            return job
