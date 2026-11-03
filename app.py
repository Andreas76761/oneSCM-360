"""oneSCM-360: local, single-user outline and document prototype."""
from __future__ import annotations

import argparse
import base64
import binascii
import io
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import uuid
import webbrowser
import zipfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
ROLES = ["Retailer", "Markt", "MO", "HQ", "intern"]
SCOPES = ["Kompakt", "Standard", "Ausführlich"]
LANGUAGES = ["de", "en", "fr", "it", "sk", "ko"]
DOMAINS = ["Product Management", "Contract Generation", "Contract Management",
           "Customer Management", "Finance Management", "Market Setting",
           "Admin Section", "Domäne 8 – reserviert"]
MAX_BODY = 8 * 1024 * 1024


class Invalid(ValueError):
    pass


class Conflict(Exception):
    pass


def uid():
    return str(uuid.uuid4())


def now():
    return datetime.now(timezone.utc).isoformat()


def profile():
    return {"role": "Retailer", "scope": "Standard", "market": "",
            "division": "Van", "language": "de", "release": "",
            "approved_only": False, "show_notes": False}


def chapter(title, level=1, mandatory=False):
    return {"id": uid(), "title": title, "level": level, "mandatory": mandatory,
            "domain": "", "goal": "", "blocks": []}


def new_outline(title):
    return {"id": uid(), "title": title, "revision": 0, "profile": profile(),
            "chapters": [chapter(t, mandatory=True) for t in ["Einleitung", "Glossar", "FAQ"]]}


def block():
    return {"id": uid(), "text": "", "source": "", "note": "", "role": "*",
            "scope": "*", "market": "*", "division": "*", "language": "de",
            "release": "*", "status": "Entwurf", "internal": False}


def clean_text(value, field, limit=10000):
    if not isinstance(value, str) or len(value) > limit or "\x00" in value:
        raise Invalid(f"Ungültiges Feld: {field}")
    return value


def choice(value, values, field):
    if value not in values:
        raise Invalid(f"Ungültige Auswahl: {field}")
    return value


def boolean(value, field):
    if not isinstance(value, bool):
        raise Invalid(f"Ungültiger Schalter: {field}")
    return value


def validate_profile(p):
    if not isinstance(p, dict):
        raise Invalid("Ausgabeprofil fehlt.")
    return {"role": choice(p.get("role"), ROLES, "Rolle"),
            "scope": choice(p.get("scope"), SCOPES, "Umfang"),
            "division": choice(p.get("division"), ["Van", "PC", "Beide"], "Sparte"),
            "language": choice(p.get("language"), LANGUAGES, "Sprache"),
            "market": clean_text(p.get("market", ""), "Markt", 100).strip(),
            "release": clean_text(p.get("release", ""), "Release", 100).strip(),
            "show_notes": boolean(p.get("show_notes", False), "Vermerke"),
            "approved_only": boolean(p.get("approved_only", False), "Freigabe")}


def validate_outline(data):
    if not isinstance(data, dict):
        raise Invalid("Gliederung fehlt.")
    result = {"id": clean_text(data.get("id"), "ID", 100),
              "title": clean_text(data.get("title"), "Titel", 200).strip(),
              "profile": validate_profile(data.get("profile")), "chapters": []}
    if not result["title"]:
        raise Invalid("Bitte einen Titel eingeben.")
    rev = data.get("revision")
    if type(rev) is not int or rev < 0:
        raise Invalid("Ungültige Revision.")
    result["revision"] = rev
    chapters = data.get("chapters")
    if not isinstance(chapters, list) or len(chapters) > 500:
        raise Invalid("Maximal 500 Kapitel pro Gliederung.")
    seen, previous = set(), 0
    for c in chapters:
        if not isinstance(c, dict):
            raise Invalid("Ungültiges Kapitel.")
        cid = clean_text(c.get("id"), "Kapitel-ID", 100)
        if not cid or cid in seen:
            raise Invalid("Kapitel-ID fehlt oder ist doppelt.")
        seen.add(cid)
        level = c.get("level")
        if type(level) is not int or not 1 <= level <= 6 or level > previous + 1:
            raise Invalid("Kapitelebenen dürfen keine Ebene überspringen.")
        previous = level
        item = {"id": cid, "title": clean_text(c.get("title"), "Kapiteltitel", 300).strip(),
                "level": level, "mandatory": boolean(c.get("mandatory", False), "Pflichtkapitel"),
                "domain": choice(c.get("domain", ""), [""] + DOMAINS, "Domäne"),
                "goal": clean_text(c.get("goal", ""), "Kapitelziel"), "blocks": []}
        if not item["title"]:
            raise Invalid("Ein Kapitel hat keinen Titel.")
        blocks = c.get("blocks", [])
        if not isinstance(blocks, list) or len(blocks) > 100:
            raise Invalid("Maximal 100 Bausteine pro Kapitel.")
        for b in blocks:
            if not isinstance(b, dict):
                raise Invalid("Ungültiger Baustein.")
            bid = clean_text(b.get("id"), "Baustein-ID", 100)
            if not bid or bid in seen:
                raise Invalid("Baustein-ID fehlt oder ist doppelt.")
            seen.add(bid)
            out = {"id": bid}
            for name in ["text", "source", "note"]:
                out[name] = clean_text(b.get(name, ""), name, 100000 if name == "text" else 10000)
            for name, values in [("role", ["*"] + ROLES), ("scope", ["*"] + SCOPES),
                                 ("division", ["*", "Van", "PC"]),
                                 ("language", LANGUAGES), ("status", ["Entwurf", "Freigegeben"])]:
                out[name] = choice(b.get(name), values, name)
            for name in ["market", "release"]:
                out[name] = clean_text(b.get(name, ""), name, 100).strip()
            out["internal"] = boolean(b.get("internal", False), "Interner Inhalt")
            item["blocks"].append(out)
        result["chapters"].append(item)
    return result


def parse_outline(text):
    clean_text(text, "Importtext", 500000)
    rows, warnings, previous = [], [], 0
    for line in text.expandtabs(2).splitlines():
        if not line.strip():
            continue
        value = line.strip()
        md = re.match(r"^(#{1,6})\s+(.+)$", value)
        numbered = re.match(r"^(\d+(?:\.\d+)*)(?:[.)])?\s+(.+)$", value)
        if md:
            level, title = len(md[1]), md[2]
        elif numbered:
            level, title = numbered[1].count(".") + 1, numbered[2]
        else:
            level = min(6, (len(line) - len(line.lstrip())) // 2 + 1)
            title = re.sub(r"^[-*•]\s+", "", value)
        adjusted = min(level, previous + 1, 6)
        if adjusted != level:
            warnings.append(f"Ebene für „{title[:60]}“ auf {adjusted} angepasst; bitte prüfen.")
        previous = adjusted
        rows.append(chapter(title[:300], adjusted, title.casefold() in {"einleitung", "glossar", "faq"}))
        if len(rows) > 500:
            raise Invalid("Maximal 500 Kapitel importieren.")
    if not rows:
        raise Invalid("Keine Kapitel erkannt.")
    return rows, warnings


def parse_docx(raw):
    from docx import Document
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if sum(f.file_size for f in archive.infolist()) > 32 * 1024 * 1024:
                raise Invalid("Die entpackte Word-Datei ist zu groß.")
        doc = Document(io.BytesIO(raw))
    except Invalid:
        raise
    except Exception as exc:
        raise Invalid("Die Datei ist kein lesbares DOCX-Dokument.") from exc
    lines = []
    for p in doc.paragraphs:
        name = p.style.name if p.style else ""
        match = re.search(r"(?:Heading|Überschrift)\s*(\d+)", name, re.I)
        if match and p.text.strip():
            lines.append("#" * min(6, int(match[1])) + " " + p.text.strip())
    if lines:
        return parse_outline("\n".join(lines))
    rows, warnings = parse_outline("\n".join(p.text for p in doc.paragraphs))
    warnings.insert(0, "Keine Überschrift-Formatvorlagen erkannt. Jeder Absatz wurde als Gliederungseintrag interpretiert.")
    return rows, warnings


def exclusion(b, p):
    if b["internal"] and p["role"] not in ["HQ", "intern"]:
        return "Interner Inhalt ist nur für HQ oder intern vorgesehen."
    for key, title in [("role", "Rolle"), ("scope", "Umfang"), ("market", "Markt"), ("release", "Release")]:
        if not b[key]:
            return f"{title} ist noch ungeklärt."
        if b[key] != "*" and b[key] != p[key]:
            return f"{title} passt nicht zum Ausgabeprofil."
    if p["division"] != "Beide" and b["division"] not in ["*", p["division"]]:
        return "Sparte passt nicht zum Ausgabeprofil."
    if b["language"] != p["language"]:
        return "Keine passende Sprachfassung in diesem Baustein."
    if p["approved_only"] and b["status"] != "Freigegeben":
        return "Baustein ist noch nicht freigegeben."
    if not b["text"].strip():
        return "Baustein enthält keinen Text."
    return None


def compose(outline, p):
    p = validate_profile(p)
    rows, warnings = [], []
    counts = [0] * 6
    for c in outline["chapters"]:
        included, excluded = [], []
        for b in c["blocks"]:
            reason = exclusion(b, p)
            if reason:
                excluded.append({"id": b["id"], "reason": reason})
            else:
                public = {k: b[k] for k in ["text", "source", "status", "division"]}
                public["note"] = b["note"] if p["show_notes"] and p["role"] in ["HQ", "intern"] else ""
                included.append(public)
        rows.append({"id": c["id"], "title": c["title"], "level": c["level"],
                     "mandatory": c["mandatory"], "blocks": included, "excluded": excluded,
                     "visible": bool(included) or c["mandatory"]})
    # Retain ancestors of visible children, then number the resulting structure.
    stack = []
    for i, row in enumerate(rows):
        while stack and rows[stack[-1]]["level"] >= row["level"]:
            stack.pop()
        if row["visible"]:
            for ancestor in stack:
                rows[ancestor]["visible"] = True
        stack.append(i)
    for row in rows:
        if row["visible"]:
            idx = row["level"] - 1
            counts[idx] += 1
            counts[idx + 1:] = [0] * (5 - idx)
            row["number"] = ".".join(str(n) for n in counts[:idx + 1])
            if row["mandatory"] and not row["blocks"]:
                warnings.append(f"Pflichtkapitel „{row['title']}“ hat keinen passenden Inhalt.")
        else:
            row["number"] = ""
    if p["show_notes"] and p["role"] not in ["HQ", "intern"]:
        warnings.append("Interne Vermerke werden nur für HQ und intern ausgegeben.")
    return {"title": outline["title"], "revision": outline["revision"],
            "profile": p, "chapters": rows, "warnings": warnings,
            "draft": True}


def profile_caption(p):
    return f"{p['role']} · {p['scope']} · {p['division']} · {p['language'].upper()} · Markt: {p['market'] or 'offen'} · Release: {p['release'] or 'offen'}"


def office_export(plan, fmt):
    output = io.BytesIO()
    caption = profile_caption(plan["profile"])
    if fmt == "docx":
        from docx import Document
        from docx.shared import Pt, RGBColor
        doc = Document()
        style = doc.styles["Normal"]
        style.font.name, style.font.size = "Calibri", Pt(11)
        doc.add_heading(plan["title"], 0)
        doc.add_paragraph("PRÜFAUSGABE · Revision " + str(plan["revision"]))
        doc.add_paragraph(caption)
        for warning in plan["warnings"]:
            doc.add_paragraph("Prüfpunkt: " + warning)
        for c in plan["chapters"]:
            if not c["visible"]:
                continue
            doc.add_heading(c["number"] + " " + c["title"], c["level"])
            if not c["blocks"] and c["mandatory"]:
                doc.add_paragraph("[Inhalt ergänzen]")
            for b in c["blocks"]:
                if plan["profile"]["division"] == "Beide" and b["division"] != "*":
                    doc.add_paragraph("Gilt für: " + b["division"], style="Caption")
                for line in b["text"].splitlines():
                    doc.add_paragraph(line)
                if b["note"]:
                    run = doc.add_paragraph("Interner Vermerk: " + b["note"]).runs[0]
                    run.font.color.rgb = RGBColor.from_string("A65112")
        doc.sections[0].footer.paragraphs[0].text = "oneSCM-360 · Prüfausgabe"
        doc.save(output)
    elif fmt == "pptx":
        from pptx import Presentation
        from pptx.util import Inches, Pt
        import textwrap
        prs = Presentation()
        prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)

        def slide(title, body):
            page = prs.slides.add_slide(prs.slide_layouts[6])
            box = page.shapes.add_textbox(Inches(.65), Inches(.4), Inches(12), Inches(1.15))
            tf = box.text_frame
            tf.word_wrap = True
            tf.text = title
            tf.paragraphs[0].font.size = Pt(26)
            bodybox = page.shapes.add_textbox(Inches(.65), Inches(1.7), Inches(12), Inches(4.9))
            bodybox.text_frame.word_wrap = True
            bodybox.text_frame.text = body
            for paragraph in bodybox.text_frame.paragraphs:
                paragraph.font.size = Pt(18)
            footer = page.shapes.add_textbox(Inches(.65), Inches(7), Inches(12), Inches(.3))
            footer.text_frame.text = f"oneSCM-360 · PRÜFAUSGABE · Revision {plan['revision']} · {len(prs.slides)}"
            footer.text_frame.paragraphs[0].font.size = Pt(10)

        def pages(title, text):
            # Explicit pagination retains all text instead of silently truncating it.
            lines = []
            for line in text.splitlines() or [""]:
                lines.extend(textwrap.wrap(line, width=80) or [""])
            for offset in range(0, len(lines), 12):
                slide(title + (" · Fortsetzung" if offset else ""), "\n".join(lines[offset:offset + 12]))

        pages(plan["title"], caption)
        if plan["warnings"]:
            pages("Offene Prüfpunkte", "\n".join(plan["warnings"]))
        for c in plan["chapters"]:
            if not c["visible"]:
                continue
            title = c["number"] + " " + c["title"]
            parts = []
            for b in c["blocks"]:
                if plan["profile"]["division"] == "Beide" and b["division"] != "*":
                    parts.append("Gilt für: " + b["division"])
                parts.append(b["text"])
                if b["note"]:
                    parts.append("Interner Vermerk: " + b["note"])
            pages(title, "\n\n".join(parts) or "[Inhalt ergänzen]")
        prs.save(output)
    else:
        raise Invalid("Ausgabeformat muss docx oder pptx sein.")
    return output.getvalue()


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS outlines(id TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS history(id TEXT, revision INTEGER, created TEXT, payload TEXT, PRIMARY KEY(id, revision));
                CREATE TABLE IF NOT EXISTS exports(id TEXT PRIMARY KEY, created TEXT, format TEXT, plan TEXT, artifact BLOB);
            """)

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def all(self):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT payload FROM outlines ORDER BY rowid")]

    def get(self, oid):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM outlines WHERE id=?", (oid,)).fetchone()
        if not row:
            raise Invalid("Gliederung nicht gefunden.")
        return json.loads(row[0])

    def save(self, data):
        data = validate_outline(data)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT revision FROM outlines WHERE id=?", (data["id"],)).fetchone()
            if (row and row[0] != data["revision"]) or (not row and data["revision"] != 0):
                raise Conflict("Die Gliederung wurde inzwischen geändert. Bitte neu laden; lokale Änderungen vorher sichern.")
            data["revision"] += 1
            payload = json.dumps(data, ensure_ascii=False)
            db.execute("INSERT OR REPLACE INTO outlines VALUES(?,?,?)", (data["id"], data["revision"], payload))
            db.execute("INSERT INTO history VALUES(?,?,?,?)", (data["id"], data["revision"], now(), payload))
        return data

    def record_export(self, plan, fmt, artifact):
        eid = uid()
        with self.connect() as db:
            db.execute("INSERT INTO exports VALUES(?,?,?,?,?)", (eid, now(), fmt, json.dumps(plan, ensure_ascii=False), artifact))
        return eid


def make_server(store, port=8765):
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, code, body, content_type="application/json; charset=utf-8", headers=None):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'none'")
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def host_valid(self):
            port = self.server.server_port
            return self.headers.get("Host") in {f"127.0.0.1:{port}", f"localhost:{port}"}

        def do_GET(self):
            if not self.host_valid():
                return self.send(403, {"error": "Nur lokaler Zugriff ist erlaubt."})
            path = urlparse(self.path).path
            if path == "/api/state":
                return self.send(200, {"token": token, "outlines": store.all(), "domains": DOMAINS,
                                       "roles": ROLES, "scopes": SCOPES, "languages": LANGUAGES})
            static = {"/": ("index.html", "text/html; charset=utf-8"),
                      "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                      "/style.css": ("style.css", "text/css; charset=utf-8")}
            if path in static:
                name, mime = static[path]
                return self.send(200, (ROOT / "web" / name).read_bytes(), mime)
            self.send(404, {"error": "Nicht gefunden."})

        def do_POST(self):
            if not self.host_valid() or self.headers.get("X-Local-Token") != token:
                return self.send(403, {"error": "Lokale Sitzung fehlt. Bitte Seite neu laden."})
            origin = self.headers.get("Origin")
            if origin and origin not in {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}:
                return self.send(403, {"error": "Ungültiger Ursprung."})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY:
                    raise Invalid("Anfrage fehlt oder ist größer als 8 MB.")
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise Invalid("Ungültige Anfrage.")
                path = urlparse(self.path).path
                if path == "/api/create":
                    return self.send(200, store.save(new_outline(clean_text(data.get("title"), "Titel", 200))))
                if path == "/api/save":
                    return self.send(200, store.save(data))
                if path == "/api/import":
                    if data.get("filename", "").lower().endswith(".docx"):
                        rows, warnings = parse_docx(base64.b64decode(data.get("base64", ""), validate=True))
                    else:
                        rows, warnings = parse_outline(data.get("text", ""))
                    return self.send(200, {"chapters": rows, "warnings": warnings})
                if path == "/api/compose":
                    outline = validate_outline(data.get("outline"))
                    return self.send(200, compose(outline, data.get("profile", outline["profile"])))
                if path == "/api/export":
                    outline = store.get(clean_text(data.get("id"), "ID", 100))
                    if outline["revision"] != data.get("revision"):
                        raise Conflict("Vor dem Export bitte den aktuellen Stand laden und speichern.")
                    plan = compose(outline, outline["profile"])
                    fmt = choice(data.get("format"), ["docx", "pptx"], "Format")
                    artifact = office_export(plan, fmt)
                    eid = store.record_export(plan, fmt, artifact)
                    return self.send(200, artifact, "application/vnd.openxmlformats-officedocument." +
                                     ("wordprocessingml.document" if fmt == "docx" else "presentationml.presentation"),
                                     {"Content-Disposition": f'attachment; filename="oneSCM-{eid[:8]}.{fmt}"'})
                self.send(404, {"error": "Nicht gefunden."})
            except Conflict as exc:
                self.send(409, {"error": str(exc)})
            except (Invalid, ValueError, TypeError, KeyError, binascii.Error) as exc:
                self.send(400, {"error": str(exc)})
            except Exception:
                self.send(500, {"error": "Verarbeitung fehlgeschlagen. Daten wurden nicht als erfolgreich bestätigt."})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    default_data = Path(os.environ.get("LOCALAPPDATA", ROOT / "data"))
    if os.name == "nt":
        default_data /= "oneSCM-360"
    parser.add_argument("--data-dir", type=Path, default=default_data)
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args()
    server = make_server(Store(args.data_dir / "onescm.sqlite3"), args.port)
    address = f"http://127.0.0.1:{server.server_port}"
    print(f"oneSCM-360 gestartet: {address}\nDatenordner: {args.data_dir}\nBeenden mit Strg+C.", flush=True)
    if args.open_browser:
        threading.Timer(.5, lambda: webbrowser.open(address)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
