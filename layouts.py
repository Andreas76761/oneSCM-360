"""Immutable native Office templates and portable HTML/PDF design settings."""
import io
import json
import re
import zipfile


def theme(value=None):
    from app import Invalid, clean_text
    defaults = {"primary": "#123443", "accent": "#00858b", "text": "#203640", "font": "Arial", "size": 11,
                "chapter": "#123443", "subchapter": "#00858b", "image_width": 100,
                "captions": True, "page_numbers": True, "icons": True, "icon_style": "symbols", "keywords": [],
                "highlight": "#fff1a8", "link": "#006b8f", "notice": "#eaf4f5",
                "exception": "#fff0e5", "tip": "#eaf5e9"}
    if value is None: return defaults
    if not isinstance(value, dict) or set(value) - set(defaults):
        raise Invalid("Ungültiges Layoutfarbschema.")
    result = {**defaults, **value}
    # Older profiles only had primary/accent. Their heading colors remain intact.
    result["chapter"] = value.get("chapter", result["primary"])
    result["subchapter"] = value.get("subchapter", result["accent"])
    for key in ["primary", "accent", "text", "chapter", "subchapter", "highlight", "link", "notice", "exception", "tip"]:
        if not isinstance(result[key], str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", result[key]):
            raise Invalid("Farben als #RRGGBB angeben.")
    result["font"] = clean_text(result["font"], "Schrift", 80)
    if not re.fullmatch(r"[\w ,.-]+", result["font"]):
        raise Invalid("Ungültiger Schriftname.")
    if type(result["size"]) is not int or not 8 <= result["size"] <= 18:
        raise Invalid("Schriftgröße zwischen 8 und 18 wählen.")
    if type(result["image_width"]) is not int or not 25 <= result["image_width"] <= 100:
        raise Invalid("Bildbreite zwischen 25 und 100 Prozent wählen.")
    for key in ["captions", "page_numbers", "icons"]:
        if type(result[key]) is not bool:
            raise Invalid("Designschalter müssen aktiviert oder deaktiviert sein.")
    if result["icon_style"] not in ["symbols", "letters", "minimal"]:
        raise Invalid("Symbolstil symbols, letters oder minimal wählen.")
    if not isinstance(result["keywords"], list) or len(result["keywords"]) > 50:
        raise Invalid("Höchstens 50 Hervorhebungsbegriffe angeben.")
    keywords, seen = [], set()
    for raw in result["keywords"]:
        keyword = clean_text(raw, "Hervorhebungsbegriff", 80).strip()
        if not keyword or "\n" in keyword or "\r" in keyword:
            raise Invalid("Hervorhebungsbegriffe einzeilig und nicht leer angeben.")
        if keyword.casefold() not in seen:
            keywords.append(keyword); seen.add(keyword.casefold())
    result["keywords"] = keywords
    return result


def selection(value):
    from app import Invalid, clean_text
    if not isinstance(value, dict) or set(value) - {"docx", "pptx", "theme"}:
        raise Invalid("Ungültige Layoutauswahl.")
    result = {"theme": theme(value.get("theme"))}
    for fmt in ["docx", "pptx"]:
        ref = value.get(fmt)
        if ref:
            if not isinstance(ref, dict) or type(ref.get("revision")) is not int or ref["revision"] < 1:
                raise Invalid("Ungültige Templaterevision.")
            result[fmt] = {"id": clean_text(ref.get("id"), "Template-ID", 100), "revision": ref["revision"]}
    return result


def _clean_package_metadata(package, properties):
    """A design template must not carry the old document preview or author metadata."""
    relationships = getattr(package, "rels", None)
    if relationships is None: relationships = package._rels
    for rel in list(relationships.values()):
        if rel.reltype.rsplit("/", 1)[-1] not in {"officeDocument", "core-properties"}:
            relationships.pop(rel.rId)
    for name in ["title", "subject", "keywords", "category", "content_status", "identifier", "language", "version", "comments"]:
        if hasattr(properties, name): setattr(properties, name, "")
    properties.author = "oneSCM-360"
    properties.last_modified_by = "oneSCM-360"


def word_document(raw):
    from copy import deepcopy
    from docx import Document
    from docx.oxml.ns import qn
    from docx.enum.section import WD_HEADER_FOOTER
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    doc = Document(io.BytesIO(raw))
    # Freeze the effective last section's headers/footers before removing earlier
    # section breaks: otherwise linked headers lose their definition.
    final_section = doc.sections[-1]
    bindings = []
    for name, kind, reltype in [
        ("header", WD_HEADER_FOOTER.PRIMARY, RT.HEADER),
        ("first_page_header", WD_HEADER_FOOTER.FIRST_PAGE, RT.HEADER),
        ("even_page_header", WD_HEADER_FOOTER.EVEN_PAGE, RT.HEADER),
        ("footer", WD_HEADER_FOOTER.PRIMARY, RT.FOOTER),
        ("first_page_footer", WD_HEADER_FOOTER.FIRST_PAGE, RT.FOOTER),
        ("even_page_footer", WD_HEADER_FOOTER.EVEN_PAGE, RT.FOOTER),
    ]:
        part = getattr(final_section, name)._get_or_add_definition()
        bindings.append((kind, reltype, part))
    for child in list(final_section._sectPr):
        if child.tag in {qn("w:headerReference"), qn("w:footerReference")}:
            final_section._sectPr.remove(child)
    active = set()
    for kind, reltype, part in bindings:
        rid = doc.part.relate_to(part, reltype); active.add(rid)
        if reltype == RT.HEADER: final_section._sectPr.add_headerReference(kind, rid)
        else: final_section._sectPr.add_footerReference(kind, rid)
    for child in list(doc._element.body):
        if child.tag != qn("w:sectPr"): doc._element.body.remove(child)
    keep = {"styles", "stylesWithEffects", "settings", "webSettings", "fontTable", "theme", "numbering", "header", "footer"}
    for rel in list(doc.part.rels.values()):
        kind = rel.reltype.rsplit("/", 1)[-1]
        if kind not in keep or kind in {"header", "footer"} and rel.rId not in active:
            doc.part.drop_rel(rel.rId)
    _clean_package_metadata(doc.part.package, doc.core_properties)
    # Office-generated templates normally contain these built-ins, but minimal
    # third-party templates can omit them. Preserve supplied styles and fill gaps.
    defaults = Document()
    for name in ["Normal", "Title", "Caption", "Table Grid"] + [f"Heading {i}" for i in range(1, 10)]:
        if name not in doc.styles:
            doc.styles.element.append(deepcopy(defaults.styles[name].element))
    return doc


def slide_document(raw):
    from pptx import Presentation
    prs = Presentation(io.BytesIO(raw))
    for slide in list(prs.slides._sldIdLst):
        prs.part.drop_rel(slide.rId)
        prs.slides._sldIdLst.remove(slide)
    # Custom shows/sections can retain slide IDs after the actual slides are gone.
    for child in list(prs.part._element):
        if child.tag.rsplit("}", 1)[-1] in {"custShowLst", "sectionLst", "extLst"}:
            prs.part._element.remove(child)
    keep = {"slideMaster", "notesMaster", "handoutMaster", "theme", "tableStyles", "presProps"}
    for rel in list(prs.part.rels.values()):
        if rel.reltype.rsplit("/", 1)[-1] not in keep: prs.part.drop_rel(rel.rId)
    _clean_package_metadata(prs.part.package, prs.core_properties)
    return prs


class Layouts:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS layouts(id TEXT PRIMARY KEY, revision INTEGER, payload TEXT);
                CREATE TABLE IF NOT EXISTS layout_history(id TEXT, revision INTEGER, payload TEXT, raw BLOB, PRIMARY KEY(id,revision));
            """)

    def listing(self):
        with self.store.connect() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT payload FROM layouts ORDER BY rowid DESC")]

    def snapshot(self, ref, fmt):
        from app import Invalid
        with self.store.connect() as db:
            row = db.execute("SELECT payload, raw FROM layout_history WHERE id=? AND revision=?", (ref["id"], ref["revision"])).fetchone()
        if not row or json.loads(row[0])["format"] != fmt:
            raise Invalid("Templateformat oder Revision nicht gefunden.")
        return json.loads(row[0]), row[1]

    def upload(self, data, raw):
        from app import Invalid, Conflict, clean_text, choice, uid, now
        fmt = choice(data.get("format"), ["docx", "pptx"], "Templateformat")
        if not raw or len(raw) > 10*1024*1024:
            raise Invalid("Office-Template bis 10 MB verwenden.")
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                if sum(f.file_size for f in archive.infolist()) > 32*1024*1024:
                    raise Invalid("Template entpackt zu groß.")
                if any("vbaproject" in n.lower() or "/embeddings/" in n.lower() for n in archive.namelist()):
                    raise Invalid("Templates ohne Makros oder eingebettete Programme verwenden.")
            if fmt == "docx": word_document(raw)
            else: slide_document(raw)
        except Invalid: raise
        except Exception as exc: raise Invalid("Template ist kein lesbares DOCX/PPTX.") from exc
        revision = data.get("revision", 0)
        if type(revision) is not int or revision < 0: raise Invalid("Templaterevision fehlt.")
        item = {"id": clean_text(data.get("id") or uid(), "ID", 100), "revision": revision+1,
                "format": fmt, "name": clean_text(data.get("name"), "Templatename", 200).strip(),
                "version": clean_text(data.get("version", "1.0"), "Templateversion", 100), "created": now()}
        if not item["name"]: raise Invalid("Templatename fehlt.")
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT revision,payload FROM layouts WHERE id=?", (item["id"],)).fetchone()
            if (old and old[0] != revision) or (not old and revision): raise Conflict("Template wurde geändert; Übersicht neu laden.")
            if old and json.loads(old[1])["format"] != fmt: raise Invalid("Format einer Templatereihe darf nicht wechseln.")
            payload = json.dumps(item, ensure_ascii=False)
            db.execute("INSERT INTO layouts VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,payload=excluded.payload", (item["id"],item["revision"],payload))
            db.execute("INSERT INTO layout_history VALUES(?,?,?,?)", (item["id"],item["revision"],payload,raw))
        return item
