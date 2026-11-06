"""Generate manual versions (Handbuchstände) per chapter: Draft, Reviewed, Released.

Stage rules (deterministic, derived from the coverage gate):
  Draft     always possible; all non-rejected claims, unreviewed ones marked
  Reviewed  only if the gate is not BLOCKED; REVIEWED and CONFIRMED claims
  Released  only if the gate is READY; CONFIRMED claims only
Output goes to 05_Manual_Generated/<Stage>/ in the local OneDrive folder as
HTML (opens in Word and browsers) and Markdown.
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone

from .claim_service import evidence_factor

STAGES = {"Draft": {"DRAFT", "REVIEWED", "CONFIRMED"}, "Reviewed": {"REVIEWED", "CONFIRMED"}, "Released": {"CONFIRMED"}}
STATUS_TEXT = {"DRAFT": "ungeprüft", "REVIEWED": "geprüft", "CONFIRMED": "freigegeben"}


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
                 coverage: dict, rules: list[dict], imports: list[dict], design: dict) -> dict:
    """Return {"html", "markdown", "stats", "title"} for one chapter and stage, formatted with a design template."""
    from .design_service import css, fill_without_pages, icon_use, symbols

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
    h = [f"<!doctype html><html lang=\"de\"><head><meta charset=\"utf-8\"><title>{e(title)}</title><style>{css(design)}</style></head><body>",
         symbols(design), '<div class="page">',
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
         f'<div class="box info">{icon_use(design, "info")}<p><strong>Hinweis zur Quellenbasis:</strong> '
         f'{e(", ".join(sources) or "noch keine abgeschlossenen Importe")}. Aussagen werden nur übernommen, wenn sie die Stufe {e(stage)} erreicht haben.</p></div>']
    if stage != "Released":
        h.append(f'<div class="box warn">{icon_use(design, "open")}<p><strong>[OFFEN – VALIDIERUNG ERFORDERLICH]</strong> '
                 "Kein freigegebener Handbuchstand. Inhalte können sich noch ändern.</p></div>")
    h.append('<div class="cols">')
    md = [f"# {title}", "", f"**Stufe:** {stage} · **Stand:** {now:%d.%m.%Y %H:%M} · **Gate:** {coverage['gate']} · "
          f"**Readiness:** {readiness} %", "", f"Quellen: {', '.join(sources) or '—'}", ""]

    group, group_no, question_no, answered = None, 0, 0, 0
    for question in chapter["questions"]:
        if question.get("group") != group:
            group = question.get("group")
            group_no += 1
            question_no = 0
            h.append(f"<h1>{group_no} {e(group or '')}</h1>")
            md += [f"## {group}", ""]
        question_no += 1
        qid = question["questionId"]
        h.append(f'<h2>{group_no}.{question_no} {e(question["title"])} <span class="src">{e(qid)}</span></h2>')
        md += [f"### {qid} · {question['title']}", ""]
        items = per_question.get(qid, [])
        refs_for_question = set()
        if items:
            answered += 1
            h.append("<ul>")
            for claim in items:
                refs = sorted({ev.get("jiraKey") or ev.get("sourceTitle") or ev.get("sourceType") for ev in by_claim.get(claim["claimId"], [])} - {""})
                refs_for_question.update(refs)
                scope = " · ".join(x for x in (claim.get("role", ""), f"PI{claim['pi']}" if claim.get("pi") is not None else "",
                                               claim.get("maturity", "")) if x)
                h.append(f"<li>{e(claim['canonicalStatement'])} {status_badge[claim['validationStatus']]} "
                         f"{division_badge.get(claim.get('division', ''), '')}"
                         + (f' <span class="src">[{e(scope)}]</span>' if scope else "") + "</li>")
                md.append(f"- {claim['canonicalStatement']}"
                          + (f" _({STATUS_TEXT[claim['validationStatus']]})_" if claim["validationStatus"] != "CONFIRMED" else "")
                          + (f" [{scope}]" if scope else "") + (f" — Quelle: {', '.join(refs)}" if refs else ""))
            h.append("</ul>")
            md.append("")
        else:
            h.append('<p class="src">Für diese Stufe liegen noch keine Inhalte vor.</p>')
            md += ["_Für diese Stufe liegen noch keine Inhalte vor._", ""]
        for table in tables_by_q.get(qid, []):
            width = table.get("columnCount") or max(len(r) for r in table["rows"])
            header = list(table.get("header") or []) or [f"Spalte {i + 1}" for i in range(width)]
            h.append("<table><tr>" + "".join(f"<th>{e(c)}</th>" for c in header) + "</tr>")
            for row in table["rows"]:
                h.append("<tr>" + "".join(f"<td>{e(row[i]) if i < len(row) else ''}</td>" for i in range(width)) + "</tr>")
            h.append(f'</table><p class="cap">Tabelle {e(table["tableId"])}</p>')
            md += ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
            md += ["| " + " | ".join((row[i] if i < len(row) else "").replace("|", "\\|") for i in range(width)) + " |" for row in table["rows"]]
            md.append("")
        if show_sources and refs_for_question:
            h.append(f'<p class="src">Quellen: {e(", ".join(sorted(refs_for_question)))}</p>')

    glossary = [r for r in rules if r["category"] in ("abbreviation", "explanation")]
    if glossary:
        h.append(f"<h1>{group_no + 1} Glossar</h1><table><tr><th>Begriff</th><th>Bedeutung</th></tr>")
        md += ["## Glossar", "", "| Begriff | Bedeutung |", "|---|---|"]
        for rule in sorted(glossary, key=lambda r: r["source"].casefold()):
            h.append(f"<tr><td>{e(rule['source'])}</td><td>{e(rule['target'])}</td></tr>")
            md.append(f"| {rule['source']} | {rule['target']} |")
        h.append("</table>")
        md.append("")
    h.append(f'</div><div class="hf"><span>{e(fill_without_pages(design["footer"], values))}</span>'
             f'<span>Designvorlage: {e(design["name"])}</span></div></div></body></html>')
    stats = {"claims": len(included), "questionsWithContent": answered, "questions": len(chapter["questions"]),
             "tables": sum(len(v) for v in tables_by_q.values()), "design": design["name"]}
    return {"html": "\n".join(h), "markdown": "\n".join(md) + "\n", "stats": stats, "title": title}


def safe_stamp() -> str:
    return re.sub(r"[^0-9-]", "", datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))
