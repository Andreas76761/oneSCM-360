"""Generate manual versions (Handbuchstände) per chapter: Draft, Reviewed, Released.

Stage rules (deterministic, derived from the coverage gate):
  Draft     always possible; all non-rejected claims, unreviewed ones marked
  Reviewed  only if the gate is not BLOCKED; REVIEWED and CONFIRMED claims
  Released  only if the gate is READY; CONFIRMED claims only
Output goes to 05_Manual_Generated/<Stage>/ in the local OneDrive folder as
HTML (opens in Word and browsers), Word (.docx with the design template's styles) and Markdown.
"""
from __future__ import annotations

import base64
import hashlib
import html
import re
from datetime import datetime, timezone
from pathlib import Path

from .claim_service import evidence_factor

STAGES = {"Draft": {"DRAFT", "REVIEWED", "CONFIRMED"}, "Reviewed": {"REVIEWED", "CONFIRMED"}, "Released": {"CONFIRMED"}}
STATUS_TEXT = {"DRAFT": "ungeprüft", "REVIEWED": "geprüft", "CONFIRMED": "freigegeben"}
HTML_IMAGES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp"}
WORD_IMAGES = {"png", "jpg", "jpeg", "gif", "bmp", "emf", "wmf"}
MAX_IMAGE_BYTES = 15 * 1024 * 1024


def manual_images(imports: list[dict], media_root: Path | None) -> dict[str, list[dict]]:
    """Images per question from completed imports: assigned to a question, marked for the manual, file present.
    The same picture from several imports (e.g. DE and EN version) appears once."""
    per_question: dict[str, list[dict]] = {}
    if media_root is None:
        return per_question
    seen = set()
    for record in imports:
        if record.get("status") != "COMPLETED":
            continue
        for item in record.get("media", []):
            qid = item.get("questionId")
            ext = item["name"].rsplit(".", 1)[-1].lower() if "." in item["name"] else ""
            if not qid or not item.get("inManual") or (ext not in HTML_IMAGES and ext not in WORD_IMAGES):
                continue
            path = Path(media_root) / record["chapterId"] / record["importId"] / item["name"]
            if not path.is_file() or path.stat().st_size > MAX_IMAGE_BYTES:
                continue
            data = path.read_bytes()
            digest = item.get("sha256") or hashlib.sha256(data).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            per_question.setdefault(qid, []).append({"data": data, "ext": ext, "alt": item.get("alt", ""), "name": item["name"],
                                                     "importId": record["importId"]})
    return per_question


class ManualError(ValueError):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


def stage_allowed(stage: str, gate: str) -> tuple[bool, str]:
    if stage not in STAGES:
        return False, "Stufe muss Draft, Reviewed oder Released sein."
    if stage == "Released" and gate != "READY":
        return False, f"Released ist nur bei Gate READY möglich (aktuell {gate})."
    if stage == "Reviewed" and gate == "BLOCKED":
        return False, "Reviewed ist bei Gate BLOCKED nicht möglich – erst die Hard Blocker auflösen."
    return True, ""


class _Output:
    """Collects the three renderings (HTML, Word body XML, Markdown) and the Word pictures of one document."""

    def __init__(self):
        self.h: list[str] = []
        self.w: list[str] = []
        self.md: list[str] = []
        self.media: list[tuple[str, str, bytes]] = []
        self.figures = 0
        self.roles: set[str] = set()


def _included(claims: list[dict], chapter_id: str, stage: str) -> list[dict]:
    return [c for c in claims if c["chapterId"] == chapter_id and c["validationStatus"] in STAGES[stage]]


def _evidence_by_claim(evidence: list[dict]) -> dict[str, list]:
    by_claim: dict[str, list] = {}
    for ev in evidence:
        if ev.get("evidenceStatus") != "REJECTED" and evidence_factor(ev) > 0:
            by_claim.setdefault(ev["claimId"], []).append(ev)
    return by_claim


def _render_questions(out: _Output, chapter: dict, included: list[dict], by_claim: dict, tables: list[dict],
                      imports: list[dict], design: dict, media_root, *, prefix: str = "", level: int = 1) -> dict:
    """Groups and questions of one chapter. level 1: group = H1, question = H2 (chapter manual);
    level 2: group = H2, question = H3 (complete manual, where the chapter is H1). prefix numbers them, e.g. "3."."""
    from . import word_template as wt
    from .design_service import role_badge

    e = html.escape
    c = design["colors"]
    status_badge = {"DRAFT": '<span class="badge b-open">Offen</span>', "REVIEWED": '<span class="badge b-both">Geprüft</span>', "CONFIRMED": ""}
    division_badge = {"PC": '<span class="badge b-pc">PC</span>', "VAN": '<span class="badge b-van">Van</span>',
                      "BOTH": '<span class="badge b-both">beide</span>', "CV": '<span class="badge b-off">CV</span>'}
    status_run = {"DRAFT": ("OFFEN", c["warn"]), "REVIEWED": ("GEPRÜFT", c["petrol"]), "CONFIRMED": None}
    division_run = {"PC": ("PC", c["pc"]), "VAN": ("VAN", c["van"]), "BOTH": ("BEIDE", c["navy"]), "CV": ("CV", c["off"])}
    show_sources = design["elements"].get("showSourceLines", True)
    per_question: dict[str, list] = {}
    for claim in included:
        per_question.setdefault(claim["questionId"], []).append(claim)
        if claim.get("role"):
            out.roles.add(claim["role"])
    tables_by_q: dict[str, list] = {}
    for table in tables:
        if table.get("sourceQuestionId") and not table.get("reviewRequired"):
            tables_by_q.setdefault(table["sourceQuestionId"], []).append(table)
    images_by_q = manual_images(imports, media_root)
    gh, qh = level, level + 1
    md_g, md_q = "#" * (level + 1), "#" * (level + 2)

    group, group_no, question_no, answered, images = None, 0, 0, 0, 0
    for question in chapter["questions"]:
        if question.get("group") != group:
            group = question.get("group")
            group_no += 1
            question_no = 0
            out.h.append(f"<h{gh}>{prefix}{group_no} {e(group or '')}</h{gh}>")
            out.w.append(wt.paragraph(f"Heading{gh}", f"{prefix}{group_no} {group or ''}"))
            out.md += [f"{md_g} {prefix}{group_no} {group}", ""]
        question_no += 1
        qid = question["questionId"]
        number = f"{prefix}{group_no}.{question_no}"
        out.h.append(f'<h{qh}>{number} {e(question["title"])} <span class="src">{e(qid)}</span></h{qh}>')
        out.md += [f"{md_q} {qid} · {question['title']}", ""]
        out.w.append(wt.paragraph(f"Heading{qh}", "", wt.run(f"{number} {question['title']} ")
                                  + wt.run(qid, color=c["muted"], size_pt=design["typography"]["source"]["size"])))
        items = per_question.get(qid, [])
        refs_for_question = set()
        if items:
            answered += 1
            out.h.append("<ul>")
            for claim in items:
                refs = sorted({ev.get("jiraKey") or ev.get("sourceTitle") or ev.get("sourceType") for ev in by_claim.get(claim["claimId"], [])} - {""})
                refs_for_question.update(refs)
                scope = " · ".join(x for x in (f"PI{claim['pi']}" if claim.get("pi") is not None else "", claim.get("maturity", "")) if x)
                role = role_badge(claim["role"], claim["role"]) if claim.get("role") else ""
                out.h.append(f"<li>{e(claim['canonicalStatement'])} {status_badge[claim['validationStatus']]} "
                             f"{division_badge.get(claim.get('division', ''), '')} {role}"
                             + (f' <span class="src">[{e(scope)}]</span>' if scope else "") + "</li>")
                tags = [x for x in (status_run[claim["validationStatus"]], division_run.get(claim.get("division", ""))) if x]
                out.w.append(wt.paragraph("ListBullet", "", wt.run(claim["canonicalStatement"])
                                          + "".join(wt.run(f"  {label}", bold=True, color=color) for label, color in tags)
                                          + (wt.run(f"  Rolle: {claim['role']}", color=c["navy"]) if claim.get("role") else "")
                                          + (wt.run(f"  [{scope}]", color=c["muted"]) if scope else "")))
                out.md.append(f"- {claim['canonicalStatement']}"
                              + (f" _({STATUS_TEXT[claim['validationStatus']]})_" if claim["validationStatus"] != "CONFIRMED" else "")
                              + (f" [{scope}]" if scope else "") + (f" — Quelle: {', '.join(refs)}" if refs else ""))
            out.h.append("</ul>")
            out.md.append("")
        else:
            out.h.append('<p class="src">Für diese Stufe liegen noch keine Inhalte vor.</p>')
            out.md += ["_Für diese Stufe liegen noch keine Inhalte vor._", ""]
            out.w.append(wt.paragraph("Quellenzeile", "Für diese Stufe liegen noch keine Inhalte vor."))
        for table in tables_by_q.get(qid, []):
            width = table.get("columnCount") or max(len(r) for r in table["rows"])
            header = list(table.get("header") or []) or [f"Spalte {i + 1}" for i in range(width)]
            out.h.append("<table><tr>" + "".join(f"<th>{e(x)}</th>" for x in header) + "</tr>")
            for row in table["rows"]:
                out.h.append("<tr>" + "".join(f"<td>{e(row[i]) if i < len(row) else ''}</td>" for i in range(width)) + "</tr>")
            out.h.append(f'</table><p class="cap">Tabelle {e(table["tableId"])}</p>')
            out.w += [wt.table(header, [[row[i] if i < len(row) else "" for i in range(width)] for row in table["rows"]], design),
                      wt.paragraph("Caption", f"Tabelle {table['tableId']}")]
            out.md += ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
            out.md += ["| " + " | ".join((row[i] if i < len(row) else "").replace("|", "\\|") for i in range(width)) + " |" for row in table["rows"]]
            out.md.append("")
        for index, picture in enumerate(images_by_q.get(qid, []), start=1):
            out.figures += 1
            images += 1
            caption = f"Abbildung {number}-{index}" + (f" – {picture['alt']}" if picture["alt"] else "")
            if picture["ext"] in HTML_IMAGES:
                uri = f"data:{HTML_IMAGES[picture['ext']]};base64,{base64.b64encode(picture['data']).decode('ascii')}"
                out.h.append(f'<figure class="shot"><img src="{uri}" alt="{e(picture["alt"] or caption)}">'
                             f'<figcaption class="cap">{e(caption)}</figcaption></figure>')
            else:
                out.h.append(f'<p class="src">{e(caption)}: {e(picture["ext"].upper())}-Grafik, nur im Word-Handbuchstand sichtbar.</p>')
            out.md += [f"_{caption}_ ({picture['name']})", ""]
            if picture["ext"] in WORD_IMAGES:
                rid, ext = f"rIdImg{out.figures}", "jpeg" if picture["ext"] == "jpg" else picture["ext"]
                out.media.append((rid, f"bild{out.figures}.{ext}", picture["data"]))
                out.w += [wt.image(design, rid, out.figures, wt.image_size(picture["data"], ext), picture["alt"] or caption),
                          wt.paragraph("Caption", caption)]
            else:
                out.w.append(wt.paragraph("Quellenzeile", f"{caption}: {picture['ext'].upper()}-Bild, in Word nicht einbettbar – siehe HTML-Handbuchstand."))
        if show_sources and refs_for_question:
            out.h.append(f'<p class="src">Quellen: {e(", ".join(sorted(refs_for_question)))}</p>')
            out.w.append(wt.paragraph("Quellenzeile", f'Quellen: {", ".join(sorted(refs_for_question))}'))
    return {"claims": len(included), "questionsWithContent": answered, "questions": len(chapter["questions"]),
            "tables": sum(len(v) for v in tables_by_q.values()), "images": images, "groups": group_no}


def _glossary(out: _Output, rules: list[dict], design: dict, heading: str):
    from . import word_template as wt
    glossary = sorted((r for r in rules if r["category"] in ("abbreviation", "explanation")), key=lambda r: r["source"].casefold())
    if not glossary:
        return
    e = html.escape
    out.h.append(f"<h1>{e(heading)}</h1><table><tr><th>Begriff</th><th>Bedeutung</th></tr>"
                 + "".join(f"<tr><td>{e(r['source'])}</td><td>{e(r['target'])}</td></tr>" for r in glossary) + "</table>")
    out.md += ["## Glossar", "", "| Begriff | Bedeutung |", "|---|---|"] + [f"| {r['source']} | {r['target']} |" for r in glossary] + [""]
    out.w += [wt.paragraph("Heading1", heading), wt.table(["Begriff", "Bedeutung"], [[r["source"], r["target"]] for r in glossary], design)]


def _head(design: dict, title: str) -> str:
    from .design_service import css
    shot_css = (f".shot{{margin:10px 0 14px;break-inside:avoid}}.shot img{{max-width:100%;max-height:16cm;border:1px solid {design['colors']['line']};"
                f"display:block}}.shot figcaption{{margin-top:4px}}.chapter-break{{break-before:page}}")
    return f"<!doctype html><html lang=\"de\"><head><meta charset=\"utf-8\"><title>{html.escape(title)}</title><style>{css(design)}{shot_css}</style></head><body>"


def _stage_texts(stage: str, design: dict):
    c = design["colors"]
    badge = {"Released": '<span class="badge b-ok">Freigegeben</span>', "Reviewed": '<span class="badge b-both">Geprüft</span>',
             "Draft": '<span class="badge b-open">Entwurf – fachliche Validierung erforderlich</span>'}[stage]
    run = {"Released": ("Freigegeben", c["ok"]), "Reviewed": ("Geprüft", c["petrol"]),
           "Draft": ("Entwurf – fachliche Validierung erforderlich", c["warn"])}[stage]
    contains = ", ".join(STATUS_TEXT[s] for s in sorted(STAGES[stage], key=list(STATUS_TEXT).index))
    return badge, run, contains


def _cover(out: _Output, design: dict, subtitle: str, meta: list[tuple[str, str]], meta_html: dict, sources: list[str] | None, stage: str):
    """Title, subtitle, metadata table, source note (unless sources is None) and, unless Released, the open-validation box."""
    from . import word_template as wt
    from .design_service import box_html
    e = html.escape
    out.h += [f'<p class="title">{e(design["documentTitle"])}</p>', f'<p class="subtitle">{e(subtitle)}</p>', '<table class="meta">']
    out.h += [f"<tr><td>{e(k)}</td><td>{meta_html.get(k, e(v))}</td></tr>" for k, v in meta if k != "Designvorlage"]
    out.h.append("</table>")
    out.w += [wt.paragraph("Title", design["documentTitle"]), wt.paragraph("Subtitle", subtitle),
              wt.table(["Angabe", "Wert"], [list(row) for row in meta], design)]
    if sources is not None:
        note = (f'{", ".join(sources) or "noch keine abgeschlossenen Importe"}. '
                f"Aussagen werden nur übernommen, wenn sie die Stufe {stage} erreicht haben.")
        out.h.append(box_html(design, "info", e(note)))
        out.w.append(wt.box(design, "info", note))
    if stage != "Released":
        out.h.append(box_html(design, "open", "Kein freigegebener Handbuchstand. Inhalte können sich noch ändern."))
        out.w.append(wt.box(design, "open", "Kein freigegebener Handbuchstand. Inhalte können sich noch ändern."))


def _finish(out: _Output, design: dict, values: dict, title: str, stage: str) -> tuple[str, bytes, str]:
    from . import word_template as wt
    from .design_service import fill_without_pages, symbols
    from .icons import role_icon
    e = html.escape
    head = [_head(design, title),
            symbols(design, {b["icon"] for b in design["boxes"]} | {role_icon(r) for r in out.roles if role_icon(r)}),
            '<div class="page">',
            f'<div class="hf top"><span>{e(fill_without_pages(design["header"], values))}</span><span>{e(stage)}</span></div>']
    tail = (f'<div class="hf"><span>{e(fill_without_pages(design["footer"], values))}</span>'
            f'<span>Designvorlage: {e(design["name"])}</span></div></div></body></html>')
    page = "\n".join(head + out.h + [tail])
    docx = wt.build_document(design, "".join(out.w), values, title, out.media)
    return page, docx, "\n".join(out.md) + "\n"


def build_manual(chapter: dict, stage: str, claims: list[dict], evidence: list[dict], tables: list[dict],
                 coverage: dict, rules: list[dict], imports: list[dict], design: dict, media_root: Path | None = None) -> dict:
    """Return {"html", "docx", "markdown", "stats", "title"} for one chapter and stage, formatted with a design template."""
    from . import word_template as wt

    included = _included(claims, chapter["chapterId"], stage)
    now = datetime.now(timezone.utc).astimezone()
    number = chapter["chapterId"][2:]
    title = f"{design['documentTitle']} – {chapter['chapterId']} {chapter['title']}"
    sources = sorted({r["sourceFile"]["name"] for r in imports if r.get("status") == "COMPLETED"})
    values = {"chapter": number, "chapterTitle": chapter["title"], "version": f"Handbuchstand {stage}", "date": f"{now:%d.%m.%Y}",
              "stage": stage, "release": "", "page": "", "pages": ""}
    readiness = f"{coverage['readiness']:.1f}".replace(".", ",")
    badge, run, contains = _stage_texts(stage, design)
    meta = [("Version", f"Handbuchstand {stage}"), ("Stand", f"{now:%d.%m.%Y %H:%M}"), ("Status", run[0]),
            ("Gate / Readiness", f"{coverage['gate']} · {readiness} %"), ("Enthaltene Aussagen", f"{len(included)} ({contains})"),
            ("Kapitelschema", chapter.get("schemaStatus", "")), ("Erstellt mit", "oneSCM360 Knowledge Studio"),
            ("Designvorlage", design["name"])]
    out = _Output()
    _cover(out, design, f"Kapitel {number} – {chapter['title']}", meta, {"Status": badge}, sources, stage)
    out.h.append('<div class="cols">')
    out.w += [wt.toc(), wt.page_break()]
    out.md += [f"# {title}", "", f"**Stufe:** {stage} · **Stand:** {now:%d.%m.%Y %H:%M} · **Gate:** {coverage['gate']} · "
               f"**Readiness:** {readiness} %", "", f"Quellen: {', '.join(sources) or '—'}", ""]
    stats = _render_questions(out, chapter, included, _evidence_by_claim(evidence), tables, imports, design, media_root)
    _glossary(out, rules, design, f"{stats.pop('groups') + 1} Glossar")
    out.h.append("</div>")
    page, docx, markdown = _finish(out, design, values, title, stage)
    return {"html": page, "docx": docx, "markdown": markdown, "stats": {**stats, "design": design["name"]}, "title": title,
            "claims": included, "chapters": [chapter["chapterId"]], "kind": "chapter"}


def build_book(entries: list[dict], stage: str, claims: list[dict], evidence: list[dict], rules: list[dict],
               design: dict, media_root: Path | None = None) -> dict:
    """Complete manual: every chapter that has a completed import and reaches the stage, one after another.

    entries: per chapter {"chapter", "coverage", "tables", "imports"} in chapter order. Chapters that are left out
    are listed in the chapter overview with the reason."""
    from . import word_template as wt

    now = datetime.now(timezone.utc).astimezone()
    title = f"{design['documentTitle']} – Gesamthandbuch"
    values = {"chapter": "CH01–CH16", "chapterTitle": "Gesamthandbuch", "version": f"Gesamthandbuch {stage}",
              "date": f"{now:%d.%m.%Y}", "stage": stage, "release": "", "page": "", "pages": ""}
    overview, selected = [], []
    for entry in entries:
        chapter, coverage = entry["chapter"], entry["coverage"]
        completed = [r for r in entry["imports"] if r.get("status") == "COMPLETED"]
        ok, reason = stage_allowed(stage, coverage["gate"])
        if not completed:
            ok, reason = False, "noch kein abgeschlossener Import"
        overview.append({"chapterId": chapter["chapterId"], "title": chapter["title"], "gate": coverage["gate"],
                         "readiness": coverage["readiness"], "included": ok, "reason": reason})
        if ok:
            selected.append(entry)
    if not selected:
        error = ManualError(f"Kein Kapitel erreicht die Stufe {stage}. Draft ist für jedes Kapitel mit abgeschlossenem Import möglich.")
        error.overview = overview  # the overview still tells why each chapter is missing
        raise error
    sources = sorted({r["sourceFile"]["name"] for entry in selected for r in entry["imports"] if r.get("status") == "COMPLETED"})
    badge, run, contains = _stage_texts(stage, design)
    included_total = sum(len(_included(claims, entry["chapter"]["chapterId"], stage)) for entry in selected)
    meta = [("Version", f"Gesamthandbuch {stage}"), ("Stand", f"{now:%d.%m.%Y %H:%M}"), ("Status", run[0]),
            ("Kapitel", f"{len(selected)} von {len(entries)}"), ("Enthaltene Aussagen", f"{included_total} ({contains})"),
            ("Erstellt mit", "oneSCM360 Knowledge Studio"), ("Designvorlage", design["name"])]
    out = _Output()
    _cover(out, design, "Gesamthandbuch", meta, {"Status": badge}, sources, stage)
    e = html.escape
    short = {"noch kein abgeschlossener Import": "kein Import"}
    rows = [[o["chapterId"], o["title"], o["gate"], f"{o['readiness']:.1f} %".replace(".", ","),
             "enthalten" if o["included"] else f"nein – {short.get(o['reason'], o['reason'])}"] for o in overview]
    header = ["Kapitel", "Titel", "Gate", "Readiness", "Im Handbuch"]
    out.h += ["<h2>Kapitelübersicht</h2>", "<table><tr>" + "".join(f"<th>{e(x)}</th>" for x in header) + "</tr>"]
    out.h += ["<tr>" + "".join(f"<td>{e(x)}</td>" for x in row) + "</tr>" for row in rows]
    out.h.append("</table>")
    out.w += [wt.paragraph("Heading2", "Kapitelübersicht"), wt.table(header, rows, design, widths=[12, 30, 21, 14, 23]), wt.toc(), wt.page_break()]
    out.md += [f"# {title}", "", f"**Stufe:** {stage} · **Stand:** {now:%d.%m.%Y %H:%M} · **Kapitel:** {len(selected)} von {len(entries)}", "",
               "| " + " | ".join(header) + " |", "|" + "---|" * len(header)] + ["| " + " | ".join(r) + " |" for r in rows] + [""]
    by_claim = _evidence_by_claim(evidence)
    per_chapter, all_included = [], []
    for index, entry in enumerate(selected, start=1):
        chapter = entry["chapter"]
        heading = f"{index} Kapitel {chapter['chapterId'][2:]} – {chapter['title']}"
        out.h.append(f'<h1 class="chapter-break">{e(heading)}</h1>')
        if index > 1:
            out.w.append(wt.page_break())
        out.w.append(wt.paragraph("Heading1", heading))
        out.md += [f"# {heading}", ""]
        included = _included(claims, chapter["chapterId"], stage)
        all_included += included
        stats = _render_questions(out, chapter, included, by_claim, entry["tables"], entry["imports"], design, media_root,
                                  prefix=f"{index}.", level=2)
        stats.pop("groups")
        per_chapter.append({"chapterId": chapter["chapterId"], **stats})
    out.w.append(wt.page_break())
    _glossary(out, rules, design, f"{len(selected) + 1} Glossar")
    page, docx, markdown = _finish(out, design, values, title, stage)
    totals = {k: sum(p[k] for p in per_chapter) for k in ("claims", "questionsWithContent", "questions", "tables", "images")}
    return {"html": page, "docx": docx, "markdown": markdown, "title": title,
            "stats": {**totals, "chapters": [p["chapterId"] for p in per_chapter], "design": design["name"]}, "overview": overview,
            "claims": all_included, "chapters": [p["chapterId"] for p in per_chapter], "kind": "book"}


def safe_stamp() -> str:
    return re.sub(r"[^0-9-]", "", datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))
