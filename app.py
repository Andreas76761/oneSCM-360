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
from contextlib import nullcontext
import domain_mapping as dm
import sources as source_module
import editorial
import library
import media
import language_workflow
import publication
import layouts
import markdown_tools
import renderers
import orchestration
import internal_knowledge
import internal_chat
import knowledge_review
import releases
import ai_exchange
from version import VERSION, RELEASE_DATE
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
ROLES = ["Retailer", "Markt", "MO", "HQ", "intern"]
SCOPES = ["Kompakt", "Standard", "Ausführlich"]
LANGUAGES = ["de", "en", "fr", "it", "sk", "ko"]
DOMAINS = dm.DOMAIN_NAMES
MAX_BODY = 32 * 1024 * 1024


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
            "approved_only": False, "show_notes": False, "as_of": "", "environment": "prod"}


def chapter(title, level=1, mandatory=False):
    return {"id": uid(), "title": title, "level": level, "mandatory": mandatory,
            "domain": "", "goal": "", "blocks": []}


def new_outline(title):
    return {"id": uid(), "title": title, "revision": 0, "profile": profile(),
            "mapping_enabled": True,
            "metadata": outline_metadata(),
            "chapters": [chapter(t, mandatory=True) for t in ["Einleitung", "Glossar", "FAQ"]]}


def outline_metadata():
    return {"version": "1.0", "document_type": "Handbuch", "status": "Entwurf",
            "owner": "", "description": "", "tags": ""}


def hydrate_outline(data):
    """Add defaults in memory; old databases and immutable history stay intact."""
    data["metadata"] = {**outline_metadata(), **data.get("metadata", {})}
    data.setdefault("created_at", "")
    data.setdefault("updated_at", "")
    data.setdefault("mapping_enabled", True)
    data.setdefault("scope_rules", editorial.scope_defaults())
    data.setdefault("validity", [])
    data.setdefault("layout", {})
    data["profile"].setdefault("as_of", "")
    data["profile"].setdefault("environment", "prod")
    data.setdefault("domain_catalog", dm.catalog())
    for c in data["chapters"]:
        c.setdefault("lineage_id", c["id"])
        if "mappings" not in c:
            c["mappings"] = dm.legacy_mappings(c)
        c.setdefault("keywords", "")
        c.setdefault("labels", "")
        c.setdefault("topic", "")
        c.setdefault("roles", [])
        c.setdefault("remarks", [])
        c.setdefault("config", editorial.defaults(c))
        c.setdefault("media", [])
        c.setdefault("media_snapshots", {})
    return data


def validate_metadata(value):
    if not isinstance(value, dict):
        raise Invalid("Metadaten müssen ein Objekt sein.")
    data = {**outline_metadata(), **value}
    result = {}
    for key, limit in [("version", 60), ("owner", 200), ("description", 5000), ("tags", 500)]:
        result[key] = clean_text(data[key], key, limit).strip()
    if not result["version"]:
        raise Invalid("Bitte eine Gliederungsversion eingeben.")
    result["document_type"] = choice(data["document_type"], ["Handbuch", "Releaseletter", "Quickreference", "Sonstiges"], "Dokumentart")
    result["status"] = choice(data["status"], ["Entwurf", "In Prüfung", "Freigegeben", "Archiviert"], "Gliederungsstatus")
    return result


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
            "approved_only": boolean(p.get("approved_only", False), "Freigabe"),
            "as_of": publication.iso_date(p.get("as_of", ""), "Stichtag"),
            "environment": choice(p.get("environment", "prod"), ["prod", "preprod"], "Umgebung")}


def validate_outline(data):
    if not isinstance(data, dict):
        raise Invalid("Gliederung fehlt.")
    result = {"id": clean_text(data.get("id"), "ID", 100),
              "title": clean_text(data.get("title"), "Titel", 200).strip(),
              "metadata": validate_metadata(data.get("metadata", {})),
              "validity": publication.validate_rules(data.get("validity", [])),
              "layout": layouts.selection(data.get("layout", {})),
              "scope_rules": editorial.validate_scopes(data.get("scope_rules", editorial.scope_defaults())),
              "mapping_enabled": boolean(data.get("mapping_enabled", True), "Domänenmapping"),
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
    seen, lineages, previous = set(), set(), 0
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
        lineage = clean_text(c.get("lineage_id", cid), "Kapitelherkunft", 100)
        if not lineage or lineage in lineages:
            raise Invalid("Kapitelherkunft fehlt oder ist doppelt.")
        lineages.add(lineage)
        item = {"id": cid, "lineage_id": lineage, "title": clean_text(c.get("title"), "Kapiteltitel", 300).strip(),
                "level": level, "mandatory": boolean(c.get("mandatory", False), "Pflichtkapitel"),
                "domain": choice(c.get("domain", ""), [""] + DOMAINS, "Domäne"),
                "mappings": dm.validate_mappings(dm.legacy_mappings(c)),
                "goal": clean_text(c.get("goal", ""), "Kapitelziel"), "blocks": []}
        item["media"] = media.validate_assignments(c.get("media", []))
        item["media_snapshots"] = c.get("media_snapshots", {})
        item["validity"] = publication.validate_rules(c.get("validity", []))
        item["config"] = editorial.validate_chapter(c)
        item["mandatory"] = item["config"]["inclusion"] == "Pflicht"
        for field in ["keywords", "labels", "topic"]:
            item[field] = clean_text(c.get(field, ""), field, 2000)
        roles = c.get("roles", [])
        if not isinstance(roles, list) or len(roles) > len(ROLES) or any(r not in ROLES for r in roles):
            raise Invalid("Ungültige Kapitelrollen.")
        item["roles"] = list(dict.fromkeys(roles))
        remarks = c.get("remarks", [])
        if not isinstance(remarks, list) or len(remarks) > 100:
            raise Invalid("Maximal 100 interne Bemerkungen je Kapitel.")
        item["remarks"] = []
        for remark in remarks:
            item["remarks"].append({"id": clean_text(remark.get("id"), "Bemerkungs-ID", 100),
                "text": clean_text(remark.get("text"), "Bemerkung", 5000),
                "color": choice(remark.get("color"), ["gelb", "blau", "grün", "rot", "violett"], "Farbe"),
                "role": choice(remark.get("role", "*"), ["*"] + ROLES, "Rolle"),
                "domain_id": clean_text(remark.get("domain_id", "*"), "Domäne", 100)})
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
            out.update(editorial.validate_block(b))
            item["blocks"].append(out)
        result["chapters"].append(item)
    return result


def compare_outlines(left, right):
    """Match known lineage first, then unambiguous paths/titles; never fuzzy-match."""
    from collections import defaultdict
    from difflib import SequenceMatcher

    def flatten(outline):
        records, stack, counts = {}, [], [0] * 6
        for c in outline["chapters"]:
            while stack and stack[-1]["level"] >= c["level"]:
                stack.pop()
            counts[c["level"] - 1] += 1
            counts[c["level"]:] = [0] * (6 - c["level"])
            path = tuple(x["title"].strip().casefold() for x in stack + [c])
            records[c["id"]] = {"chapter": c, "parent": stack[-1]["id"] if stack else None,
                                 "path": path, "number": ".".join(map(str, counts[:c["level"]]))}
            stack.append(c)
        return records

    a, b = flatten(left), flatten(right)
    matches, basis = {}, {}
    for method, key in [("Kennung", lambda r: r["chapter"].get("lineage_id", r["chapter"]["id"])),
                        ("Kapitelpfad", lambda r: r["path"]),
                        ("Eindeutiger Titel", lambda r: r["chapter"]["title"].strip().casefold())]:
        # Ambiguous keys stay ambiguous even if one other occurrence was already matched.
        group_a, group_b = defaultdict(list), defaultdict(list)
        for cid, r in a.items():
            group_a[key(r)].append(cid)
        for cid, r in b.items():
            group_b[key(r)].append(cid)
        used = set(matches.values())
        for value, ids in group_a.items():
            other = group_b.get(value, [])
            if len(ids) == len(other) == 1 and ids[0] not in matches and other[0] not in used:
                matches[ids[0]] = other[0]
                basis[ids[0]] = method
                used.add(other[0])
    reverse = {v: k for k, v in matches.items()}
    moved = set()
    groups = defaultdict(list)
    for aid, bid in matches.items():
        ap, bp = a[aid]["parent"], b[bid]["parent"]
        if (ap is None and bp is None) or (ap in matches and matches[ap] == bp):
            groups[ap].append(aid)
        else:
            moved.add(aid)
    # Insertion/deletion alone must not mark every following sibling as moved.
    for parent, ids in groups.items():
        old = [cid for cid in a if cid in ids]
        new = [reverse[cid] for cid in b if cid in reverse and reverse[cid] in ids]
        stable = set()
        for match in SequenceMatcher(a=old, b=new, autojunk=False).get_matching_blocks():
            stable.update(old[match.a:match.a + match.size])
        moved.update(set(ids) - stable)

    flags, changed_fields = {}, {}
    counts = {name: 0 for name in ["added", "removed", "renamed", "moved", "changed", "unchanged"]}
    for aid, bid in matches.items():
        ac, bc = a[aid]["chapter"], b[bid]["chapter"]
        values, fields = [], []
        if ac["title"] != bc["title"]:
            values.append("renamed")
        if aid in moved:
            values.append("moved")
        for field in ["mandatory", "goal", "keywords", "labels", "topic", "roles", "remarks", "config", "media", "media_snapshots", "validity"]:
            if ac.get(field) != bc.get(field):
                fields.append(field)
        if dm.signature(left, ac) != dm.signature(right, bc):
            fields.append("mappings")
        blocks_a = [{k: v for k, v in x.items() if k != "id"} for x in ac["blocks"]]
        blocks_b = [{k: v for k, v in x.items() if k != "id"} for x in bc["blocks"]]
        if blocks_a != blocks_b:
            fields.append("blocks")
        if fields:
            values.append("changed")
        flags[aid] = values or ["unchanged"]
        changed_fields[aid] = fields
        for value in flags[aid]:
            counts[value] += 1
    counts["removed"] = len(a) - len(matches)
    counts["added"] = len(b) - len(matches)

    def tree(records, left_side):
        nodes, roots = {}, []
        for cid, record in records.items():
            aid = cid if left_side else reverse.get(cid)
            peer = matches.get(cid) if left_side else reverse.get(cid)
            c = record["chapter"]
            node = {"id": cid, "title": c["title"], "number": record["number"],
                    "mandatory": c["mandatory"], "children": [], "peer_id": peer,
                    "flags": flags[aid] if peer else ["removed" if left_side else "added"],
                    "match_basis": basis.get(aid, ""), "changed_fields": changed_fields.get(aid, [])}
            nodes[cid] = node
            (nodes[record["parent"]]["children"] if record["parent"] else roots).append(node)
        return roots

    changes = []
    for key in ["validity", "layout"]:
        if left.get(key) != right.get(key):
            changes.append({"field": key, "left": left.get(key), "right": right.get(key)})
    if left.get("scope_rules", editorial.scope_defaults()) != right.get("scope_rules", editorial.scope_defaults()):
        changes.append({"field": "scope_rules", "left": left.get("scope_rules"), "right": right.get("scope_rules")})
    if left.get("mapping_enabled", True) != right.get("mapping_enabled", True):
        changes.append({"field": "mapping_enabled", "left": left.get("mapping_enabled", True),
                        "right": right.get("mapping_enabled", True)})
    for field, before, after in [("title", left["title"], right["title"])]:
        if before != after:
            changes.append({"field": field, "left": before, "right": after})
    for section in ["metadata", "profile"]:
        for field in left[section]:
            if left[section][field] != right[section][field]:
                changes.append({"field": section + "." + field, "left": left[section][field], "right": right[section][field]})
    return {"left": tree(a, True), "right": tree(b, False), "counts": counts,
            "metadata_changes": changes,
            "left_label": f"{left['title']} · V{left['metadata']['version']} · R{left['revision']}",
            "right_label": f"{right['title']} · V{right['metadata']['version']} · R{right['revision']}"}


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
    plan = editorial.compose(outline, p)
    plan["manifest"]["application"] = {"version": VERSION, "date": RELEASE_DATE}
    return plan


def profile_caption(p):
    return f"{p['role']} · {p['scope']} · {p['division']} · {p['language'].upper()} · Markt: {p['market'] or 'offen'} · Release: {p['release'] or 'offen'} · {p.get('environment', 'prod')} · Stichtag: {p.get('as_of') or 'offen'}"


def office_export(plan, fmt, media_loader=None, template_bytes=None):
    output = io.BytesIO()
    caption = profile_caption(plan["profile"])
    output_label = "PRÜFAUSGABE" if plan.get("draft", True) else "FREIGEGEBENE AUSGABE"
    design = layouts.theme(plan.get("layout", {}).get("theme"))
    if fmt == "docx":
        from docx import Document
        from docx.shared import Pt, RGBColor, Inches
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from copy import deepcopy
        doc = layouts.word_document(template_bytes) if template_bytes else Document()
        style = doc.styles["Normal"]
        if not template_bytes:
            style.font.name, style.font.size = design["font"], Pt(design["size"])
            style.font.color.rgb = RGBColor.from_string(design["text"][1:])
            doc.styles["Title"].font.color.rgb = RGBColor.from_string(design["primary"][1:])
            doc.styles["Caption"].font.color.rgb = RGBColor.from_string(design["accent"][1:])
            for level in range(1, 10):
                doc.styles[f"Heading {level}"].font.color.rgb = RGBColor.from_string(design["chapter" if level == 1 else "subchapter"][1:])
        doc.add_heading(plan["title"], 0)
        doc.add_paragraph(output_label + " · Version " + plan["metadata"]["version"] + " · Revision " + str(plan["revision"]))
        doc.add_paragraph(caption)
        for warning in plan["warnings"]:
            doc.add_paragraph("Prüfpunkt: " + warning)
        for c in plan["chapters"]:
            if not c["visible"]:
                continue
            doc.add_heading(c["number"] + " " + c["title"], c["level"])
            if not c["blocks"] and not c.get("figures") and c["mandatory"]:
                doc.add_paragraph("[Inhalt ergänzen]")
            for b in c["blocks"]:
                if plan["profile"]["division"] == "Beide" and b["division"] != "*":
                    doc.add_paragraph("Gilt für: " + b["division"], style="Caption")
                if b.get("text_format") == "markdown":
                    markdown_tools.append_word(doc, b["text"], min(6, c["level"]))
                else:
                    for line in b["text"].splitlines():
                        doc.add_paragraph(line)
            for figure in c.get("figures", []):
                if figure["title"]:
                    doc.add_paragraph(figure["title"], style="Caption")
                for frame in figure["frames"]:
                    if not media_loader:
                        raise Invalid("Bilddaten für Ausgabe fehlen.")
                    section = doc.sections[-1]
                    available = (section.page_width-section.left_margin-section.right_margin)/914400
                    width = min(available*design["image_width"]/100, 8.0 * frame["width"] / frame["height"])
                    doc.add_picture(io.BytesIO(media_loader(frame["asset_id"], frame["revision"])), width=Inches(width))
                    caption = (f"Schritt {frame['step']}: " if figure["kind"] == "Klickstrecke" else "") + frame["caption"]
                    if caption and design["captions"]:
                        doc.add_paragraph(caption, style="Caption")
        # Decorate reader content only, including paragraphs in Markdown tables.
        # Splitting simple runs retains bold/italic formatting and hyperlink parents.
        for paragraph in doc._element.body.iter(qn("w:p")):
            text = "".join(node.text or "" for node in paragraph.iter(qn("w:t")))
            kind = renderers.callout_kind(text)
            if kind:
                props = paragraph.get_or_add_pPr()
                shade = OxmlElement("w:shd"); shade.set(qn("w:fill"),design[kind][1:]); props.append(shade)
                if design["icons"]:
                    run = OxmlElement("w:r"); node = OxmlElement("w:t");node.set(qn("xml:space"),"preserve")
                    node.text = renderers.callout_icon(kind,design)+" ";run.append(node);paragraph.insert(1,run)
            for run in list(paragraph.iter(qn("w:r"))):
                if run.getparent().tag == qn("w:hyperlink"):
                    props=run.get_or_add_rPr();color=props.find(qn("w:color"))
                    if color is None: color=OxmlElement("w:color");props.append(color)
                    color.set(qn("w:val"),design["link"][1:])
                if any(node.tag not in {qn("w:rPr"),qn("w:t")} for node in run): continue
                text="".join(node.text or "" for node in run.findall(qn("w:t")))
                segments=renderers.keyword_segments(text,design)
                if not any(marked for _,marked in segments): continue
                parent=run.getparent();position=parent.index(run)
                for value,marked in segments:
                    replacement=deepcopy(run)
                    for node in list(replacement):
                        if node.tag != qn("w:rPr"): replacement.remove(node)
                    node=OxmlElement("w:t");node.set(qn("xml:space"),"preserve");node.text=value;replacement.append(node)
                    if marked:
                        shade=OxmlElement("w:shd");shade.set(qn("w:fill"),design["highlight"][1:]);replacement.get_or_add_rPr().append(shade)
                    parent.insert(position,replacement);position+=1
                parent.remove(run)
        if not template_bytes:
            footer = doc.sections[0].footer.paragraphs[0]
            footer.text = "oneSCM-360 · " + output_label
        else:
            footer = doc.sections[0].footer.add_paragraph("oneSCM-360 · " + output_label)
        existing_fields = [node.text or "" for node in doc.sections[0].footer._element.iter(qn("w:instrText"))]
        existing_fields += [node.get(qn("w:instr"),"") for node in doc.sections[0].footer._element.iter(qn("w:fldSimple"))]
        if design["page_numbers"] and not any(re.search(r"\bPAGE\b", text, re.I) for text in existing_fields):
            footer.add_run(" · ")
            field = OxmlElement("w:fldSimple");field.set(qn("w:instr"),"PAGE");footer._p.append(field)
        doc.save(output)
    elif fmt == "pptx":
        from pptx import Presentation
        from pptx.util import Inches, Pt
        from pptx.dml.color import RGBColor
        from pptx.enum.shapes import MSO_SHAPE
        from pptx.oxml.xmlchemy import OxmlElement
        import textwrap
        prs = layouts.slide_document(template_bytes) if template_bytes else Presentation()
        if not template_bytes:
            prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
        sx, sy = prs.slide_width / Inches(13.333), prs.slide_height / Inches(7.5)
        X = lambda value: Inches(value * sx)
        Y = lambda value: Inches(value * sy)
        blank = min(prs.slide_layouts, key=lambda layout: len(layout.placeholders))
        body_size = max(14,min(26,design["size"]*1.6))
        line_points = body_size*1.3+4

        def slide(title, body, level=1, links=None):
            links = links or {}
            page = prs.slides.add_slide(blank)
            box = page.shapes.add_textbox(X(.65), Y(.4), X(12), Y(1.15))
            tf = box.text_frame
            tf.word_wrap = True
            tf.text = title
            tf.paragraphs[0].font.size = Pt(26)
            if not template_bytes:
                tf.paragraphs[0].font.name = design["font"]
                tf.paragraphs[0].font.color.rgb = RGBColor.from_string(design["chapter" if level == 1 else "subchapter"][1:])
            for index,line in enumerate(body.split("\n")):
                kind = renderers.callout_kind(line)
                if kind:
                    badge = page.shapes.add_shape(MSO_SHAPE.RECTANGLE,X(.65),Y(1.7)+Pt(index*line_points),X(12),Pt(line_points))
                    badge.fill.solid();badge.fill.fore_color.rgb=RGBColor.from_string(design[kind][1:]);badge.line.fill.background()
            bodybox = page.shapes.add_textbox(X(.65), Y(1.7), X(12), Y(4.9))
            bodybox.text_frame.word_wrap = True
            bodybox.text_frame.text = body
            for paragraph in bodybox.text_frame.paragraphs:
                text=paragraph.text;kind=renderers.callout_kind(text)
                if kind and design["icons"]: text=renderers.callout_icon(kind,design)+" "+text
                paragraph.clear();paragraph.font.size = Pt(body_size)
                paragraph.line_spacing=Pt(body_size*1.3);paragraph.space_after=Pt(4)
                if not template_bytes:
                    paragraph.font.name=design["font"];paragraph.font.color.rgb=RGBColor.from_string(design["text"][1:])
                labels=sorted(links,key=len,reverse=True)
                pattern="("+"|".join(re.escape(label) for label in labels)+")" if labels else None
                for part in re.split(pattern,text) if pattern else [text]:
                    for value,marked in renderers.keyword_segments(part,design):
                        run=paragraph.add_run();run.text=value
                        if part in links:
                            run.hyperlink.address=links[part];run.font.color.rgb=RGBColor.from_string(design["link"][1:]);run.font.underline=True
                        if marked:
                            highlight=OxmlElement("a:highlight");color=OxmlElement("a:srgbClr");color.set("val",design["highlight"][1:]);highlight.append(color);run._r.get_or_add_rPr().append(highlight)
            footer = page.shapes.add_textbox(X(.65), Y(7), X(12), Y(.3))
            footer.text_frame.text = f"oneSCM-360 · {output_label} · Revision {plan['revision']}" + (f" · {len(prs.slides)}" if design["page_numbers"] else "")
            footer.text_frame.paragraphs[0].font.size = Pt(10)
            if not template_bytes: footer.text_frame.paragraphs[0].font.color.rgb=RGBColor.from_string(design["accent"][1:])

        def pages(title, text, level=1, links=None):
            # Explicit pagination retains all text instead of silently truncating it.
            lines = []
            for line in text.splitlines() or [""]:
                lines.extend(textwrap.wrap(line, width=max(20,int(80*sx*18/body_size))) or [""])
            page_lines=max(1,int(4.65*72*sy/line_points))
            for offset in range(0, len(lines), page_lines):
                slide(title + (" · Fortsetzung" if offset else ""), "\n".join(lines[offset:offset + page_lines]),level,links)

        pages(plan["title"], "Version " + plan["metadata"]["version"] + "\n" + caption)
        if plan["warnings"]:
            pages("Offene Prüfpunkte", "\n".join(plan["warnings"]))
        for c in plan["chapters"]:
            if not c["visible"]:
                continue
            title = c["number"] + " " + c["title"]
            parts = []
            links = {}
            for b in c["blocks"]:
                if plan["profile"]["division"] == "Beide" and b["division"] != "*":
                    parts.append("Gilt für: " + b["division"])
                if b.get("text_format") == "markdown":
                    text,block_links=renderers.slide_markdown(b["text"]);parts.append(text);links.update(block_links)
                else: parts.append(b["text"])
            if parts or not c.get("figures"):
                pages(title, "\n\n".join(parts) or "[Inhalt ergänzen]",c["level"],links)
            for figure in c.get("figures", []):
                for frame in figure["frames"]:
                    if not media_loader:
                        raise Invalid("Bilddaten für Ausgabe fehlen.")
                    heading = title + (f" · Schritt {frame['step']}" if figure["kind"] == "Klickstrecke" else "")
                    slide(heading, "",c["level"])
                    page = prs.slides[-1]
                    width = min(11.8*sx*design["image_width"]/100, 4.4*sy * frame["width"] / frame["height"])
                    height = width * frame["height"] / frame["width"]
                    page.shapes.add_picture(io.BytesIO(media_loader(frame["asset_id"], frame["revision"])), Inches((13.333*sx-width)/2), Y(1.65), width=Inches(width), height=Inches(height))
                    if not design["captions"]: continue
                    caption = page.shapes.add_textbox(X(.65), Y(6.2), X(12), Y(.65))
                    caption.text_frame.word_wrap = True
                    caption.text_frame.text = frame["caption"] if len(frame["caption"]) <= 240 else "Bildunterschrift auf der folgenden Folie."
                    for paragraph in caption.text_frame.paragraphs:
                        paragraph.font.size = Pt(14)
                        if not template_bytes: paragraph.font.color.rgb=RGBColor.from_string(design["accent"][1:])
                    if len(frame["caption"]) > 240:
                        pages(heading + " · Bildunterschrift", frame["caption"])
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
                CREATE TABLE IF NOT EXISTS taxonomy(singleton INTEGER PRIMARY KEY CHECK(singleton=1), revision INTEGER NOT NULL, payload TEXT NOT NULL);
                INSERT OR IGNORE INTO taxonomy VALUES(1, 0, '[]');
            """)
        self.sources = source_module.Sources(self)
        self.sources.init()
        self.library = library.Library(self)
        self.media = media.Media(self)
        self.layouts = layouts.Layouts(self)
        self.orchestrator = orchestration.Orchestrator(self)
        self.internal = internal_knowledge.InternalKnowledge(self)
        self.review = knowledge_review.KnowledgeReview(self)
        self.chat = internal_chat.InternalChat(self)
        self.releases = releases.Releases(self)
        self.ai_exchange = ai_exchange.Exchange(self)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def get_catalog(self):
        return dm.catalog(self.taxonomy()["subdomains"])

    def taxonomy(self):
        with self.connect() as db:
            revision, payload = db.execute("SELECT revision, payload FROM taxonomy WHERE singleton=1").fetchone()
        return {"revision": revision, "subdomains": json.loads(payload), "domains": dm.MAIN_DOMAINS}

    def save_taxonomy(self, data):
        if type(data.get("revision")) is not int:
            raise Invalid("Die Revision der Unterdomänen fehlt.")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rev, payload = db.execute("SELECT revision, payload FROM taxonomy WHERE singleton=1").fetchone()
            if rev != data["revision"]:
                raise Conflict("Die Unterdomänen wurden inzwischen geändert. Bitte den Dialog schließen und erneut öffnen.")
            rows = dm.validate_subdomains(data.get("subdomains"), json.loads(payload))
            db.execute("UPDATE taxonomy SET revision=?, payload=? WHERE singleton=1", (rev + 1, json.dumps(rows, ensure_ascii=False)))
        return {"revision": rev + 1, "subdomains": rows, "domains": dm.MAIN_DOMAINS}

    def all(self):
        with self.connect() as db:
            return [hydrate_outline(json.loads(r[0])) for r in db.execute("SELECT payload FROM outlines ORDER BY rowid")]

    def get(self, oid):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM outlines WHERE id=?", (oid,)).fetchone()
        if not row:
            raise Invalid("Gliederung nicht gefunden.")
        return hydrate_outline(json.loads(row[0]))

    def history(self, oid):
        with self.connect() as db:
            rows = db.execute("SELECT revision, created, payload FROM history WHERE id=? ORDER BY revision DESC", (oid,)).fetchall()
        return [{"revision": r[0], "created": r[1], "title": json.loads(r[2])["title"],
                 "metadata": hydrate_outline(json.loads(r[2]))["metadata"]} for r in rows]

    def snapshot(self, oid, revision=None):
        if revision is None:
            return self.get(oid)
        if type(revision) is not int or revision < 1:
            raise Invalid("Ungültige Vergleichsrevision.")
        with self.connect() as db:
            row = db.execute("SELECT payload FROM history WHERE id=? AND revision=?", (oid, revision)).fetchone()
        if not row:
            raise Invalid("Die ausgewählte Revision existiert nicht.")
        return hydrate_outline(json.loads(row[0]))

    def save(self, data, releasing=False, connection=None):
        data = self.media.resolve(self.library.resolve(data))
        metadata_supplied = "metadata" in data
        mapping_supplied = "mapping_enabled" in data
        supplied_chapters = {c["id"] for c in data.get("chapters", []) if "mappings" in c}
        data = validate_outline(data)
        for fmt in ["docx", "pptx"]:
            if data["layout"].get(fmt): self.layouts.snapshot(data["layout"][fmt], fmt)
        with (self.connect() if connection is None else nullcontext(connection)) as db:
            if connection is None:
                db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT revision, payload FROM outlines WHERE id=?", (data["id"],)).fetchone()
            if (row and row[0] != data["revision"]) or (not row and data["revision"] != 0):
                raise Conflict("Die Gliederung wurde inzwischen geändert. Bitte neu laden; lokale Änderungen vorher sichern.")
            previous = hydrate_outline(json.loads(row[1])) if row else None
            if previous and not metadata_supplied:
                data["metadata"] = previous["metadata"]
            if previous and not mapping_supplied:
                data["mapping_enabled"] = previous["mapping_enabled"]
            old_chapters = {c["id"]: c for c in previous["chapters"]} if previous else {}
            for c in data["chapters"]:
                if c["id"] not in supplied_chapters and c["id"] in old_chapters:
                    old = old_chapters[c["id"]]
                    if "mappings" in old and c["domain"] != old["domain"]:
                        raise Conflict("Die Domänenzuordnung wurde in einer älteren Oberfläche geändert. Bitte die Seite neu laden und Mehrfachzuordnungen verwenden.")
                    c["mappings"] = old["mappings"]
            subdomains = json.loads(db.execute("SELECT payload FROM taxonomy WHERE singleton=1").fetchone()[0])
            for c in data["chapters"]:
                for item in c["media"]:
                    for frame in item["frames"]:
                        for ref in frame["variants"]:
                            if not db.execute("SELECT 1 FROM media_history WHERE id=? AND revision=?", (ref["asset_id"], ref["revision"])).fetchone():
                                raise Conflict("Eine Bildrevision wurde inzwischen gelöscht. Medienzuordnung erneut prüfen.")
            data["domain_catalog"] = dm.catalog(subdomains)
            valid_targets = {d["id"] for d in data["domain_catalog"]}
            for c in data["chapters"]:
                c["mappings"] = dm.validate_mappings(c["mappings"], valid_targets)
            if releasing:
                errors = editorial.release_errors(compose(data, data["profile"]))
                if errors:
                    raise Invalid("Freigabe nicht möglich: " + " | ".join(errors))
                data["metadata"]["status"] = "Freigegeben"
            elif data["metadata"]["status"] == "Freigegeben":
                # Content edits always start a new draft revision; approval is explicit.
                data["metadata"]["status"] = "Entwurf"
            stamp = now()
            data["created_at"] = previous["created_at"] if previous else stamp
            data["updated_at"] = stamp
            data["revision"] += 1
            payload = json.dumps(data, ensure_ascii=False)
            db.execute("INSERT INTO outlines VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision, payload=excluded.payload", (data["id"], data["revision"], payload))
            db.execute("INSERT INTO history VALUES(?,?,?,?)", (data["id"], data["revision"], now(), payload))
            valid_chapters = {c["id"] for c in data["chapters"]}
            for (cid,) in db.execute("SELECT DISTINCT chapter_id FROM assignments WHERE outline_id=?", (data["id"],)).fetchall():
                if cid not in valid_chapters:
                    db.execute("DELETE FROM assignments WHERE outline_id=? AND chapter_id=?", (data["id"], cid))
        return data

    def copy(self, oid):
        data = self.get(oid)
        data["id"], data["revision"] = uid(), 0
        data["title"] = data["title"][:190] + " – Kopie"
        data["metadata"]["status"] = "Entwurf"
        chapter_ids = {}
        for c in data["chapters"]:
            old_id = c["id"]
            c["id"] = uid()  # lineage_id is retained for reliable comparisons.
            chapter_ids[old_id] = c["id"]
            for b in c["blocks"]:
                b["id"] = uid()
        saved = self.save(data)
        with self.connect() as db:
            for old, new in chapter_ids.items():
                db.execute("INSERT INTO assignments SELECT chunk_id, ?, ? FROM assignments WHERE outline_id=? AND chapter_id=?", (saved["id"], new, oid, old))
        return saved

    def usage(self, oid):
        self.get(oid)
        with self.connect() as db:
            exports = []
            for eid, created, fmt, raw in db.execute("SELECT id, created, format, plan FROM exports ORDER BY created DESC"):
                plan = json.loads(raw)
                if plan.get("outline_id") == oid:
                    exports.append({"id": eid, "created": created, "format": fmt,
                                    "revision": plan["revision"], "profile": plan["profile"],
                                    "draft": plan.get("draft", True), "manifest": plan.get("manifest", {})})
            links = db.execute("SELECT a.chapter_id, c.id, s.name FROM assignments a JOIN chunks c ON c.id=a.chunk_id JOIN sources s ON s.id=c.source_id WHERE a.outline_id=?", (oid,)).fetchall()
        return {"exports": exports, "chunks": [{"chapter_id": r[0], "chunk_id": r[1], "source": r[2]} for r in links]}

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
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data: blob:; script-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'none'")
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
                return self.send(200, {"token": token, "build": {"version": VERSION, "date": RELEASE_DATE}, "outlines": store.all(), "domains": DOMAINS,
                                       "taxonomy": store.taxonomy(),
                                       "chunk_index": store.sources.index(),
                                       "roles": ROLES, "scopes": SCOPES, "languages": LANGUAGES})
            static = {"/design.js": ("design.js", "text/javascript; charset=utf-8"),
                      "/design.css": ("design.css", "text/css; charset=utf-8"),
                      "/ai_exchange.js": ("ai_exchange.js", "text/javascript; charset=utf-8"),
                      "/": ("index.html", "text/html; charset=utf-8"),
                      "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                      "/management.js": ("management.js", "text/javascript; charset=utf-8"),
                      "/management.css": ("management.css", "text/css; charset=utf-8"),
                      "/mapping.js": ("mapping.js", "text/javascript; charset=utf-8"),
                      "/mapping.css": ("mapping.css", "text/css; charset=utf-8"),
                      "/matrix.js": ("matrix.js", "text/javascript; charset=utf-8"),
                      "/internal.js": ("internal.js", "text/javascript; charset=utf-8"),
                      "/knowledge.js": ("knowledge.js", "text/javascript; charset=utf-8"),
                      "/knowledge.css": ("knowledge.css", "text/css; charset=utf-8"),
                      "/publishing.js": ("publishing.js", "text/javascript; charset=utf-8"),
                      "/publishing.css": ("publishing.css", "text/css; charset=utf-8"),
                      "/jobs.js": ("jobs.js", "text/javascript; charset=utf-8"),
                      "/media.js": ("media.js", "text/javascript; charset=utf-8"),
                      "/media.css": ("media.css", "text/css; charset=utf-8"),
                      "/library.js": ("library.js", "text/javascript; charset=utf-8"),
                      "/editorial.js": ("editorial.js", "text/javascript; charset=utf-8"),
                      "/editorial.css": ("editorial.css", "text/css; charset=utf-8"),
                      "/sources.js": ("sources.js", "text/javascript; charset=utf-8"),
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
                    raise Invalid("Anfrage fehlt oder ist größer als 32 MB (Quelldateien bis 20 MB).")
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise Invalid("Ungültige Anfrage.")
                path = urlparse(self.path).path
                if path == "/api/chat/list":
                    return self.send(200, store.chat.listing())
                if path == "/api/chat/get":
                    return self.send(200, store.chat.get(clean_text(data.get("id"), "Chat-ID", 100)))
                if path == "/api/chat/ask":
                    return self.send(200, store.chat.ask(data))
                if path == "/api/review/state":
                    with store.connect() as db:
                        scans = [json.loads(r[0]) for r in db.execute("SELECT payload FROM knowledge_scans ORDER BY rowid DESC LIMIT 50")]
                    return self.send(200, {"reviews":store.review.listing(), "contexts":store.review.contexts(), "sources":store.sources.listing(), "scans":scans})
                if path == "/api/review/context":
                    return self.send(200, store.review.save_context(data))
                if path == "/api/review/scan":
                    return self.send(200, store.review.scan(data))
                if path == "/api/review/inspect":
                    return self.send(200, store.review.inspect(data))
                if path == "/api/review/decide":
                    return self.send(200, store.review.decide(data))
                if path == "/api/review/history":
                    return self.send(200, store.review.history(clean_text(data.get("id"), "Prüfpunkt-ID", 100)))
                if path == "/api/releases":
                    return self.send(200, store.releases.listing())
                if path == "/api/release/prepare":
                    return self.send(200, store.releases.prepare(data))
                if path == "/api/release/promote":
                    return self.send(200, store.releases.promote(data))
                if path == "/api/release/rollback":
                    return self.send(200, store.releases.rollback(data))
                if path == "/api/internal":
                    return self.send(200, {"categories":store.internal.categories(),"entries":store.internal.listing()})
                if path == "/api/internal/save":
                    return self.send(200, store.internal.save(data))
                if path == "/api/internal/categories":
                    return self.send(200, store.internal.save_categories(data))
                if path == "/api/internal/history":
                    return self.send(200, store.internal.history(clean_text(data.get("id"), "Interne ID", 100)))
                if path == "/api/internal/chatbot-preview":
                    return self.send(200, store.internal.chatbot_preview(data))
                if path == "/api/jobs":
                    return self.send(200, store.orchestrator.listing())
                if path == "/api/job/start":
                    return self.send(200, store.orchestrator.start(data))
                if path == "/api/job/get":
                    return self.send(200, store.orchestrator.get(clean_text(data.get("id"), "Lauf-ID", 100)))
                if path == "/api/job/step":
                    return self.send(200, store.orchestrator.step(clean_text(data.get("id"), "Lauf-ID", 100)))
                if path == "/api/job/cancel":
                    return self.send(200, store.orchestrator.cancel(clean_text(data.get("id"), "Lauf-ID", 100)))
                if path == "/api/job/report":
                    job = store.orchestrator.get(clean_text(data.get("id"), "Lauf-ID", 100))
                    if not job.get("report_markdown"):
                        raise Invalid("Noch kein Dokumentationsbericht vorhanden.")
                    return self.send(200, job["report_markdown"].encode(), "text/markdown; charset=utf-8", {"Content-Disposition": 'attachment; filename="Finalisierungsbericht.md"'})
                if path == "/api/job/apply":
                    return self.send(200, store.orchestrator.apply(data))
                if path.startswith("/api/ai-exchange/"):
                    action = path.rsplit("/", 1)[-1]
                    if action == "list":
                        return self.send(200, store.ai_exchange.listing())
                    if action in {"prepare", "preview", "accept"}:
                        return self.send(200, getattr(store.ai_exchange, action)(data))
                if path == "/api/layouts":
                    return self.send(200, store.layouts.listing())
                if path == "/api/layout/upload":
                    return self.send(200, store.layouts.upload(data, base64.b64decode(data.get("base64", ""), validate=True)))
                if path == "/api/markdown/convert":
                    template = store.layouts.snapshot(data["template"], "docx")[1] if data.get("template") else None
                    artifact, fmt = markdown_tools.batch(data.get("files"), data.get("combined") is True, data.get("title", "Markdown-Dokumente"), template)
                    return self.send(200, artifact, renderers.MIME[fmt], {"Content-Disposition": f'attachment; filename="Markdown-Konvertierung.{fmt}"'})
                if path == "/api/source/paste":
                    fmt = choice(data.get("format", "txt"), ["txt", "html", "md"], "Zwischenablageformat")
                    name = clean_text(data.get("name", "Zwischenablage"), "Name", 200) + "." + fmt
                    raw = clean_text(data.get("text"), "Zwischenablage", 1_000_000).encode()
                    return self.send(200, store.sources.upload(name, raw, data))
                if path == "/api/timeline":
                    with store.connect() as db:
                        rows = []
                        for oid,rev,created,raw in db.execute("SELECT id,revision,created,payload FROM history ORDER BY created DESC"):
                            entry = hydrate_outline(json.loads(raw))
                            rows.append({"id":oid,"revision":rev,"created":created,"title":entry["title"],"metadata":entry["metadata"],"profile":entry["profile"],"validity":entry.get("validity",[])})
                    return self.send(200, rows)
                if path == "/api/applicability":
                    outline = validate_outline(store.media.resolve(store.library.resolve(data.get("outline"))))
                    return self.send(200, publication.matrix(outline))
                if path == "/api/sources":
                    return self.send(200, {"sources": store.sources.listing(), "chunk_index": store.sources.index()})
                if path == "/api/source/upload":
                    raw = base64.b64decode(data.get("base64", ""), validate=True)
                    return self.send(200, store.sources.upload(data.get("name"), raw, data))
                if path == "/api/source/import/start":
                    return self.send(200, store.sources.imports.start(data.get("name"), base64.b64decode(data.get("base64", ""), validate=True), data))
                if path == "/api/source/import/list":
                    return self.send(200, store.sources.imports.listing())
                if path == "/api/source/import/step":
                    return self.send(200, store.sources.imports.step(data))
                if path == "/api/source/import/cancel":
                    return self.send(200, store.sources.imports.cancel(data))
                if path == "/api/source/chunks":
                    return self.send(200, store.sources.chunks(clean_text(data.get("id"), "Quellen-ID", 100)))
                if path == "/api/source/delete":
                    store.sources.delete(clean_text(data.get("id"), "Quellen-ID", 100))
                    return self.send(200, {"deleted": True})
                if path == "/api/source/review":
                    return self.send(200, store.sources.review(data, {d["id"] for d in dm.catalog(store.taxonomy()["subdomains"])}))
                if path == "/api/source/triage":
                    return self.send(200, store.sources.triage(clean_text(data.get("id"), "Quellen-ID", 100),
                        store.get(clean_text(data.get("outline_id"), "Gliederungs-ID", 100)),
                        dm.catalog(store.taxonomy()["subdomains"]), data.get("mode"), data.get("model", ""), data.get("offset", 0)))
                if path == "/api/media":
                    return self.send(200, store.media.listing())
                if path in ["/api/media/upload", "/api/media/save", "/api/media/ocr", "/api/media/preview", "/api/media/extract", "/api/media/delete"]:
                    if data.get("working_role") not in ["HQ", "intern"]:
                        raise Invalid("Medienbearbeitung erfordert Redaktionsrolle HQ oder intern.")
                if path == "/api/media/delete":
                    store.media.delete(clean_text(data.get("id"), "Bild-ID", 100))
                    return self.send(200, {"deleted": True})
                if path == "/api/media/extract":
                    return self.send(200, store.media.extract_source(clean_text(data.get("id"), "Quellen-ID", 100), data.get("language", "de")))
                if path == "/api/media/upload":
                    return self.send(200, store.media.upload(base64.b64decode(data.get("base64", ""), validate=True), data.get("name"), data.get("language", "de"), data.get("metadata", {})))
                if path == "/api/media/save":
                    return self.send(200, store.media.save(data))
                if path == "/api/media/ocr":
                    result = store.media.ocr(clean_text(data.get("id"), "Bild-ID", 100))
                    if data.get("outline_id"):
                        outline = store.get(clean_text(data["outline_id"], "Gliederungs-ID", 100))
                        result["classification"] = source_module.rules({"text": result["text"]}, outline, store.get_catalog())
                        ids = set(result["classification"]["chapter_ids"])
                        result["chapter_titles"] = [c["title"] for c in outline["chapters"] if c["id"] in ids]
                    return self.send(200, result)
                if path == "/api/media/preview":
                    raw = media.render(store.media.original(clean_text(data.get("id"), "Bild-ID", 100)), data.get("redactions", []), data.get("markers", []))
                    return self.send(200, {"image": "data:image/png;base64," + base64.b64encode(raw).decode()})
                if path == "/api/media/image":
                    raw = store.media.image(clean_text(data.get("id"), "Bild-ID", 100), data.get("revision"), data.get("working_role"), data.get("original") is True)
                    return self.send(200, {"image": "data:image/png;base64," + base64.b64encode(raw).decode()})
                if path == "/api/library":
                    return self.send(200, store.library.listing())
                if path == "/api/library/language":
                    entry = store.library.snapshot({"id": data.get("id"), "revision": data.get("revision")})
                    return self.send(200, language_workflow.generate(entry, data.get("mode"), data.get("target"), data.get("model")))
                if path == "/api/library/collect":
                    return self.send(200, store.library.collection(data.get("outline"), data.get("chapter_id")))
                if path == "/api/library/save":
                    return self.send(200, store.library.save(data))
                if path == "/api/reimport":
                    base = store.get(clean_text(data.get("id"), "ID", 100))
                    if base["revision"] != data.get("revision"):
                        raise Conflict("Gliederung wurde geändert. Import erneut prüfen.")
                    result = editorial.reimport(base, data.get("chapters"), data.get("decisions"))
                    if data.get("apply") is True:
                        if result["unresolved"]:
                            raise Invalid("Bitte alle unklaren Kapitelzuordnungen entscheiden.")
                        return self.send(200, store.save(result["outline"]))
                    return self.send(200, result)
                if path == "/api/release":
                    outline = store.get(clean_text(data.get("id"), "ID", 100))
                    if outline["revision"] != data.get("revision"):
                        raise Conflict("Gliederung wurde geändert. Freigabe erneut prüfen.")
                    return self.send(200, store.save(outline, releasing=True))
                if path == "/api/usage":
                    return self.send(200, store.usage(clean_text(data.get("id"), "ID", 100)))
                if path == "/api/export/history":
                    with store.connect() as db:
                        row = db.execute("SELECT format, artifact FROM exports WHERE id=?", (clean_text(data.get("id"), "Ausgabe-ID", 100),)).fetchone()
                    if not row:
                        raise Invalid("Ausgabe nicht gefunden.")
                    return self.send(200, row[1], "application/octet-stream")
                if path == "/api/create":
                    return self.send(200, store.save(new_outline(clean_text(data.get("title"), "Titel", 200))))
                if path == "/api/save":
                    return self.send(200, store.save(data))
                if path == "/api/taxonomy":
                    return self.send(200, store.taxonomy())
                if path == "/api/taxonomy/save":
                    return self.send(200, store.save_taxonomy(data))
                if path == "/api/domain-map":
                    outline = validate_outline(data.get("outline"))
                    return self.send(200, dm.grouped(outline, dm.catalog(store.taxonomy()["subdomains"]),
                                                     boolean(data.get("include_inactive", False), "Inaktive Zuordnungen")))
                if path == "/api/copy":
                    return self.send(200, store.copy(clean_text(data.get("id"), "ID", 100)))
                if path == "/api/history":
                    return self.send(200, store.history(clean_text(data.get("id"), "ID", 100)))
                if path == "/api/compare":
                    left = store.snapshot(clean_text(data.get("left_id"), "Linke ID", 100), data.get("left_revision"))
                    right = store.snapshot(clean_text(data.get("right_id"), "Rechte ID", 100), data.get("right_revision"))
                    return self.send(200, compare_outlines(left, right))
                if path == "/api/import":
                    if data.get("filename", "").lower().endswith(".docx"):
                        rows, warnings = parse_docx(base64.b64decode(data.get("base64", ""), validate=True))
                    else:
                        rows, warnings = parse_outline(data.get("text", ""))
                    return self.send(200, {"chapters": rows, "warnings": warnings})
                if path == "/api/compose":
                    outline = validate_outline(store.media.resolve(store.library.resolve(data.get("outline"))))
                    return self.send(200, compose(outline, data.get("profile", outline["profile"])))
                if path == "/api/export":
                    outline = store.get(clean_text(data.get("id"), "ID", 100))
                    if outline["revision"] != data.get("revision"):
                        raise Conflict("Vor dem Export bitte den aktuellen Stand laden und speichern.")
                    plan = compose(outline, outline["profile"])
                    if data.get("published") is True:
                        errors = editorial.release_errors(plan)
                        if outline["metadata"]["status"] != "Freigegeben" or errors:
                            raise Invalid("Für eine Veröffentlichung zuerst alle Prüfpunkte bearbeiten und die Gliederung freigeben.")
                        plan["draft"] = False
                    fmt = choice(data.get("format"), ["docx", "pptx", "html", "pdf"], "Format")
                    loader = lambda aid, rev: store.media.image(aid, rev, "intern")
                    template = None
                    if fmt in ["docx", "pptx"] and outline.get("layout", {}).get(fmt):
                        info, template = store.layouts.snapshot(outline["layout"][fmt], fmt)
                        plan["manifest"]["template"] = info
                        plan["manifest"]["template_version"] = info["version"]
                    plan["manifest"]["theme"] = layouts.theme(outline.get("layout", {}).get("theme"))
                    artifact = renderers.html_export(plan, loader) if fmt == "html" else renderers.pdf_export(plan, loader) if fmt == "pdf" else office_export(plan, fmt, loader, template)
                    eid = store.record_export(plan, fmt, artifact)
                    return self.send(200, artifact, renderers.MIME[fmt], {"Content-Disposition": f'attachment; filename="oneSCM-{eid[:8]}.{fmt}"'})

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
    try:
        server = make_server(Store(args.data_dir / "onescm.sqlite3"), args.port)
    except OSError as exc:
        if exc.errno in {48, 98, 10048} or getattr(exc, "winerror", None) == 10048:
            parser.exit(1, f"Port {args.port} ist bereits belegt. Die bisherige oneSCM-Instanz im alten Konsolenfenster mit Strg+C beenden und dann diese start.bat erneut starten.\nProgrammordner dieser Version: {ROOT}\n")
        raise
    address = f"http://127.0.0.1:{server.server_port}"
    print(f"oneSCM-360 v{VERSION} · {RELEASE_DATE} gestartet: {address}\nProgrammordner: {ROOT}\nDatenordner: {args.data_dir}\nBeenden mit Strg+C.", flush=True)
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
