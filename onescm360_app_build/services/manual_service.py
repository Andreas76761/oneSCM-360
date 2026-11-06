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


def build_manual(chapter: dict, stage: str, claims: list[dict], evidence: list[dict], tables: list[dict],
                 coverage: dict, rules: list[dict], imports: list[dict], design: dict, media_root: Path | None = None) -> dict:
    """Return {"html", "docx", "markdown", "stats", "title"} for one chapter and stage, formatted with a design template."""
    from . import word_template as wt
    from .design_service import box_html, css, fill_without_pages, role_badge, symbols
    from .icons import role_icon

    allowed_status = STAGES[stage]
    by_claim: dict[str, list] = {}
    for ev in evidence:
        if ev.get("evidenceStatus") != "REJECTED" and evidence_factor(ev) > 0:
            by_claim.setdefault(ev["claimId"], []).append(ev)
    included = [c for c in claims if c["chapterId"] == chapter["chapterId"] and c["validationStatus"] in allowed_status]
    per_question: dict[str, list] = {}
    for claim in included:
        per_question.setdefault(claim["questionId"], []).append(claim)
    tables_by_q: dict[str, list] = {}
    for table in tables:
        if table.get("sourceQuestionId") and not table.get("reviewRequired"):
            tables_by_q.setdefault(table["sourceQuestionId"], []).append(table)

    images_by_q = manual_images(imports, media_root)
    word_media: list[tuple[str, str, bytes]] = []
    figure_no = 0
    now = datetime.now(timezone.utc).astimezone()
    number = chapter["chapterId"][2:]
    title = f"{design['documentTitle']} – {chapter['chapterId']} {chapter['title']}"
    sources = sorted({r["sourceFile"]["name"] for r in imports if r.get("status") == "COMPLETED"})
    values = {"chapter": number, "chapterTitle": chapter["title"], "version": f"Handbuchstand {stage}", "date": f"{now:%d.%m.%Y}",
              "stage": stage, "release": "", "page": "", "pages": ""}
    e = html.escape
    readiness = f"{coverage['readiness']:.1f}".replace(".", ",")
    stage_badge = {"Released": '<span class="badge b-ok">Freigegeben</span>', "Reviewed": '<span class="badge b-both">Geprüft</span>',
                   "Draft": '<span class="badge b-open">Entwurf – fachliche Validierung erforderlich</span>'}[stage]
    status_badge = {"DRAFT": '<span class="badge b-open">Offen</span>', "REVIEWED": '<span class="badge b-both">Geprüft</span>', "CONFIRMED": ""}
    division_badge = {"PC": '<span class="badge b-pc">PC</span>', "VAN": '<span class="badge b-van">Van</span>',
                      "BOTH": '<span class="badge b-both">beide</span>', "CV": '<span class="badge b-off">CV</span>'}
    show_sources = design["elements"].get("showSourceLines", True)
    shot_css = (f".shot{{margin:10px 0 14px;break-inside:avoid}}.shot img{{max-width:100%;max-height:16cm;border:1px solid {design['colors']['line']};"
                f"display:block}}.shot figcaption{{margin-top:4px}}")
    h = [f"<!doctype html><html lang=\"de\"><head><meta charset=\"utf-8\"><title>{e(title)}</title><style>{css(design)}{shot_css}</style></head><body>",
         symbols(design, {b["icon"] for b in design["boxes"]} | {role_icon(r) for r in {c.get("role") for c in included} if role_icon(r)}),
         '<div class="page">',
         f'<div class="hf top"><span>{e(fill_without_pages(design["header"], values))}</span><span>{e(stage)}</span></div>',
         f'<p class="title">{e(design["documentTitle"])}</p>',
         f'<p class="subtitle">Kapitel {e(number)} – {e(chapter["title"])}</p>',
         '<table class="meta">',
         f"<tr><td>Version</td><td>Handbuchstand {e(stage)}</td></tr>",
         f"<tr><td>Stand</td><td>{now:%d.%m.%Y %H:%M}</td></tr>",
         f"<tr><td>Status</td><td>{stage_badge}</td></tr>",
         f"<tr><td>Gate / Readiness</td><td>{e(coverage['gate'])} · {readiness} %</td></tr>",
         f"<tr><td>Enthaltene Aussagen</td><td>{len(included)} ({', '.join(STATUS_TEXT[s] for s in sorted(allowed_status, key=list(STATUS_TEXT).index))})</td></tr>",
         f"<tr><td>Kapitelschema</td><td>{e(chapter.get('schemaStatus', ''))}</td></tr>",
         "<tr><td>Erstellt mit</td><td>oneSCM360 Knowledge Studio</td></tr>",
         "</table>",
         box_html(design, "info", f'{e(", ".join(sources) or "noch keine abgeschlossenen Importe")}. '
                                  f"Aussagen werden nur übernommen, wenn sie die Stufe {e(stage)} erreicht haben.")]
    if stage != "Released":
        h.append(box_html(design, "open", "Kein freigegebener Handbuchstand. Inhalte können sich noch ändern."))
    h.append('<div class="cols">')
    c = design["colors"]
    stage_run = {"Released": ("Freigegeben", c["ok"]), "Reviewed": ("Geprüft", c["petrol"]),
                 "Draft": ("Entwurf – fachliche Validierung erforderlich", c["warn"])}[stage]
    status_run = {"DRAFT": ("OFFEN", c["warn"]), "REVIEWED": ("GEPRÜFT", c["petrol"]), "CONFIRMED": None}
    division_run = {"PC": ("PC", c["pc"]), "VAN": ("VAN", c["van"]), "BOTH": ("BEIDE", c["navy"]), "CV": ("CV", c["off"])}
    meta = [("Version", f"Handbuchstand {stage}"), ("Stand", f"{now:%d.%m.%Y %H:%M}"), ("Status", stage_run[0]),
            ("Gate / Readiness", f"{coverage['gate']} · {readiness} %"),
            ("Enthaltene Aussagen", f"{len(included)} ({', '.join(STATUS_TEXT[s] for s in sorted(allowed_status, key=list(STATUS_TEXT).index))})"),
            ("Kapitelschema", chapter.get("schemaStatus", "")), ("Erstellt mit", "oneSCM360 Knowledge Studio"),
            ("Designvorlage", design["name"])]
    w = [wt.paragraph("Title", design["documentTitle"]), wt.paragraph("Subtitle", f"Kapitel {number} – {chapter['title']}"),
         wt.table(["Angabe", "Wert"], [list(row) for row in meta], design),
         wt.box(design, "info", f'{", ".join(sources) or "noch keine abgeschlossenen Importe"}. '
                                f"Aussagen werden nur übernommen, wenn sie die Stufe {stage} erreicht haben.")]
    if stage != "Released":
        w.append(wt.box(design, "open", "Kein freigegebener Handbuchstand. Inhalte können sich noch ändern."))
    w += [wt.toc(), wt.page_break()]
    md = [f"# {title}", "", f"**Stufe:** {stage} · **Stand:** {now:%d.%m.%Y %H:%M} · **Gate:** {coverage['gate']} · "
          f"**Readiness:** {readiness} %", "", f"Quellen: {', '.join(sources) or '—'}", ""]

    group, group_no, question_no, answered = None, 0, 0, 0
    for question in chapter["questions"]:
        if question.get("group") != group:
            group = question.get("group")
            group_no += 1
            question_no = 0
            h.append(f"<h1>{group_no} {e(group or '')}</h1>")
            w.append(wt.paragraph("Heading1", f"{group_no} {group or ''}"))
            md += [f"## {group}", ""]
        question_no += 1
        qid = question["questionId"]
        h.append(f'<h2>{group_no}.{question_no} {e(question["title"])} <span class="src">{e(qid)}</span></h2>')
        md += [f"### {qid} · {question['title']}", ""]
        w.append(wt.paragraph("Heading2", "", wt.run(f"{group_no}.{question_no} {question['title']} ")
                              + wt.run(qid, color=c["muted"], size_pt=design["typography"]["source"]["size"])))
        items = per_question.get(qid, [])
        refs_for_question = set()
        if items:
            answered += 1
            h.append("<ul>")
            for claim in items:
                refs = sorted({ev.get("jiraKey") or ev.get("sourceTitle") or ev.get("sourceType") for ev in by_claim.get(claim["claimId"], [])} - {""})
                refs_for_question.update(refs)
                scope = " · ".join(x for x in (f"PI{claim['pi']}" if claim.get("pi") is not None else "", claim.get("maturity", "")) if x)
                role = role_badge(claim["role"], claim["role"]) if claim.get("role") else ""
                h.append(f"<li>{e(claim['canonicalStatement'])} {status_badge[claim['validationStatus']]} "
                         f"{division_badge.get(claim.get('division', ''), '')} {role}"
                         + (f' <span class="src">[{e(scope)}]</span>' if scope else "") + "</li>")
                tags = [x for x in (status_run[claim["validationStatus"]], division_run.get(claim.get("division", ""))) if x]
                w.append(wt.paragraph("ListBullet", "", wt.run(claim["canonicalStatement"])
                                      + "".join(wt.run(f"  {label}", bold=True, color=color) for label, color in tags)
                                      + (wt.run(f"  Rolle: {claim['role']}", color=c["navy"]) if claim.get("role") else "")
                                      + (wt.run(f"  [{scope}]", color=c["muted"]) if scope else "")))
                md.append(f"- {claim['canonicalStatement']}"
                          + (f" _({STATUS_TEXT[claim['validationStatus']]})_" if claim["validationStatus"] != "CONFIRMED" else "")
                          + (f" [{scope}]" if scope else "") + (f" — Quelle: {', '.join(refs)}" if refs else ""))
            h.append("</ul>")
            md.append("")
        else:
            h.append('<p class="src">Für diese Stufe liegen noch keine Inhalte vor.</p>')
            md += ["_Für diese Stufe liegen noch keine Inhalte vor._", ""]
            w.append(wt.paragraph("Quellenzeile", "Für diese Stufe liegen noch keine Inhalte vor."))
        for table in tables_by_q.get(qid, []):
            width = table.get("columnCount") or max(len(r) for r in table["rows"])
            header = list(table.get("header") or []) or [f"Spalte {i + 1}" for i in range(width)]
            h.append("<table><tr>" + "".join(f"<th>{e(c)}</th>" for c in header) + "</tr>")
            for row in table["rows"]:
                h.append("<tr>" + "".join(f"<td>{e(row[i]) if i < len(row) else ''}</td>" for i in range(width)) + "</tr>")
            h.append(f'</table><p class="cap">Tabelle {e(table["tableId"])}</p>')
            w += [wt.table(header, [[row[i] if i < len(row) else "" for i in range(width)] for row in table["rows"]], design),
                  wt.paragraph("Caption", f"Tabelle {table['tableId']}")]
            md += ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
            md += ["| " + " | ".join((row[i] if i < len(row) else "").replace("|", "\\|") for i in range(width)) + " |" for row in table["rows"]]
            md.append("")
        for number, picture in enumerate(images_by_q.get(qid, []), start=1):
            figure_no += 1
            caption = f"Abbildung {group_no}.{question_no}-{number}" + (f" – {picture['alt']}" if picture["alt"] else "")
            if picture["ext"] in HTML_IMAGES:
                uri = f"data:{HTML_IMAGES[picture['ext']]};base64,{base64.b64encode(picture['data']).decode('ascii')}"
                h.append(f'<figure class="shot"><img src="{uri}" alt="{e(picture["alt"] or caption)}">'
                         f'<figcaption class="cap">{e(caption)}</figcaption></figure>')
            else:
                h.append(f'<p class="src">{e(caption)}: {e(picture["ext"].upper())}-Grafik, nur im Word-Handbuchstand sichtbar.</p>')
            md.append(f"_{caption}_ ({picture['name']})")
            md.append("")
            if picture["ext"] in WORD_IMAGES:
                rid, ext = f"rIdImg{figure_no}", "jpeg" if picture["ext"] == "jpg" else picture["ext"]
                word_media.append((rid, f"bild{figure_no}.{ext}", picture["data"]))
                w += [wt.image(design, rid, figure_no, wt.image_size(picture["data"], ext), picture["alt"] or caption),
                      wt.paragraph("Caption", caption)]
            else:
                w.append(wt.paragraph("Quellenzeile", f"{caption}: {picture['ext'].upper()}-Bild, in Word nicht einbettbar – siehe HTML-Handbuchstand."))
        if show_sources and refs_for_question:
            h.append(f'<p class="src">Quellen: {e(", ".join(sorted(refs_for_question)))}</p>')
            w.append(wt.paragraph("Quellenzeile", f'Quellen: {", ".join(sorted(refs_for_question))}'))

    glossary = [r for r in rules if r["category"] in ("abbreviation", "explanation")]
    if glossary:
        h.append(f"<h1>{group_no + 1} Glossar</h1><table><tr><th>Begriff</th><th>Bedeutung</th></tr>")
        md += ["## Glossar", "", "| Begriff | Bedeutung |", "|---|---|"]
        w += [wt.paragraph("Heading1", f"{group_no + 1} Glossar"),
              wt.table(["Begriff", "Bedeutung"], [[r["source"], r["target"]] for r in sorted(glossary, key=lambda r: r["source"].casefold())], design)]
        for rule in sorted(glossary, key=lambda r: r["source"].casefold()):
            h.append(f"<tr><td>{e(rule['source'])}</td><td>{e(rule['target'])}</td></tr>")
            md.append(f"| {rule['source']} | {rule['target']} |")
        h.append("</table>")
        md.append("")
    h.append(f'</div><div class="hf"><span>{e(fill_without_pages(design["footer"], values))}</span>'
             f'<span>Designvorlage: {e(design["name"])}</span></div></div></body></html>')
    stats = {"claims": len(included), "questionsWithContent": answered, "questions": len(chapter["questions"]),
             "tables": sum(len(v) for v in tables_by_q.values()), "images": figure_no, "design": design["name"]}
    docx = wt.build_document(design, "".join(w), values, title, word_media)
    return {"html": "\n".join(h), "docx": docx, "markdown": "\n".join(md) + "\n", "stats": stats, "title": title}


def safe_stamp() -> str:
    return re.sub(r"[^0-9-]", "", datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))
