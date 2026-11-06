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
                 coverage: dict, rules: list[dict], imports: list[dict]) -> dict:
    """Return {"html", "markdown", "stats"} for one chapter and stage."""
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
    title = f"oneSCM360 Handbuch – {chapter['chapterId']} {chapter['title']}"
    sources = sorted({r["sourceFile"]["name"] for r in imports if r.get("status") == "COMPLETED"})
    e = html.escape
    h = [f"<!doctype html><html lang=\"de\"><head><meta charset=\"utf-8\"><title>{e(title)}</title><style>"
         "body{font-family:'Segoe UI',Arial,sans-serif;max-width:900px;margin:32px auto;padding:0 20px;color:#1d2733;line-height:1.5}"
         "h1{font-size:24px}h2{font-size:18px;margin-top:28px;border-bottom:1px solid #dbe1e7;padding-bottom:4px}"
         "h3{font-size:15px;margin:18px 0 6px}table{border-collapse:collapse;margin:8px 0 14px;width:100%}"
         "th,td{border:1px solid #c5ced8;padding:5px 8px;text-align:left;vertical-align:top;font-size:13px}th{background:#f1f4f7}"
         ".meta td:first-child{width:200px;color:#5d6b7a}.stage{display:inline-block;padding:3px 10px;border-radius:999px;font-weight:600}"
         ".Draft{background:#fdf1d8;color:#8a5a00}.Reviewed{background:#e8eef9;color:#1d3c6e}.Released{background:#e3f4ea;color:#1f7a46}"
         ".flag{font-size:11px;color:#8a5a00;border:1px solid #f0d9a6;border-radius:4px;padding:0 4px;margin-left:4px}"
         ".src{font-size:11px;color:#5d6b7a}.empty{color:#8a95a1;font-style:italic}"
         "@media print{body{margin:0}}</style></head><body>",
         f"<h1>{e(title)}</h1>",
         f"<p><span class=\"stage {stage}\">{stage}</span></p>",
         "<table class=\"meta\">",
         f"<tr><td>Stand</td><td>{now:%d.%m.%Y %H:%M}</td></tr>",
         f"<tr><td>Kapitelschema</td><td>{e(chapter.get('schemaStatus', ''))}</td></tr>",
         f"<tr><td>Gate / Readiness</td><td>{e(coverage['gate'])} · {coverage['readiness']:.1f} %</td></tr>",
         f"<tr><td>Enthaltene Aussagen</td><td>{len(included)} ({', '.join(STATUS_TEXT[s] for s in sorted(allowed_status, key=list(STATUS_TEXT).index))})</td></tr>",
         f"<tr><td>Quellen</td><td>{e(', '.join(sources) or '—')}</td></tr>",
         "</table>"]
    if stage != "Released":
        h.append("<p class=\"empty\">Kein freigegebener Handbuchstand. Inhalte können sich noch ändern.</p>")
    md = [f"# {title}", "", f"**Stufe:** {stage} · **Stand:** {now:%d.%m.%Y %H:%M} · **Gate:** {coverage['gate']} · "
          f"**Readiness:** {coverage['readiness']:.1f} %", "", f"Quellen: {', '.join(sources) or '—'}", ""]

    group = None
    answered = 0
    for question in chapter["questions"]:
        if question.get("group") != group:
            group = question.get("group")
            h.append(f"<h2>{e(group or '')}</h2>")
            md += [f"## {group}", ""]
        qid = question["questionId"]
        h.append(f"<h3>{e(qid)} · {e(question['title'])}</h3>")
        md += [f"### {qid} · {question['title']}", ""]
        items = per_question.get(qid, [])
        if items:
            answered += 1
            h.append("<ul>")
            for claim in items:
                refs = sorted({ev.get("jiraKey") or ev.get("sourceTitle") or ev.get("sourceType") for ev in by_claim.get(claim["claimId"], [])} - {""})
                flag = f"<span class=\"flag\">{STATUS_TEXT[claim['validationStatus']]}</span>" if claim["validationStatus"] != "CONFIRMED" else ""
                scope = " · ".join(x for x in (claim.get("role", ""), claim.get("division", ""), f"PI{claim['pi']}" if claim.get("pi") is not None else "",
                                               claim.get("maturity", "")) if x)
                h.append(f"<li>{e(claim['canonicalStatement'])}{flag}"
                         + (f" <span class=\"src\">[{e(scope)}]</span>" if scope else "")
                         + (f" <span class=\"src\">Quelle: {e(', '.join(refs))}</span>" if refs else "") + "</li>")
                md.append(f"- {claim['canonicalStatement']}" + (f" _({STATUS_TEXT[claim['validationStatus']]})_" if flag else "")
                          + (f" [{scope}]" if scope else "") + (f" — Quelle: {', '.join(refs)}" if refs else ""))
            h.append("</ul>")
            md.append("")
        else:
            h.append("<p class=\"empty\">Für diese Stufe liegen noch keine Inhalte vor.</p>")
            md += ["_Für diese Stufe liegen noch keine Inhalte vor._", ""]
        for table in tables_by_q.get(qid, []):
            width = table.get("columnCount") or max(len(r) for r in table["rows"])
            header = list(table.get("header") or []) or [f"Spalte {i + 1}" for i in range(width)]
            h.append(f"<table><caption class=\"src\">{e(table['tableId'])}</caption><tr>" + "".join(f"<th>{e(c)}</th>" for c in header) + "</tr>")
            for row in table["rows"]:
                h.append("<tr>" + "".join(f"<td>{e(row[i]) if i < len(row) else ''}</td>" for i in range(width)) + "</tr>")
            h.append("</table>")
            md += ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
            md += ["| " + " | ".join((row[i] if i < len(row) else "").replace("|", "\\|") for i in range(width)) + " |" for row in table["rows"]]
            md.append("")

    glossary = [r for r in rules if r["category"] in ("abbreviation", "explanation")]
    if glossary:
        h.append("<h2>Glossar</h2><table><tr><th>Begriff</th><th>Bedeutung</th></tr>")
        md += ["## Glossar", "", "| Begriff | Bedeutung |", "|---|---|"]
        for rule in sorted(glossary, key=lambda r: r["source"].casefold()):
            h.append(f"<tr><td>{e(rule['source'])}</td><td>{e(rule['target'])}</td></tr>")
            md.append(f"| {rule['source']} | {rule['target']} |")
        h.append("</table>")
        md.append("")
    h.append("<p class=\"src\">Erzeugt durch oneSCM360 Knowledge Studio. Der Transfer nach SharePoint erfolgt manuell.</p></body></html>")
    stats = {"claims": len(included), "questionsWithContent": answered, "questions": len(chapter["questions"]),
             "tables": sum(len(v) for v in tables_by_q.values())}
    return {"html": "\n".join(h), "markdown": "\n".join(md) + "\n", "stats": stats, "title": title}


def safe_stamp() -> str:
    return re.sub(r"[^0-9-]", "", datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))
