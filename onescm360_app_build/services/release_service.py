"""Release letters: what changed in the manual since an earlier manual version.

Every generated manual version (chapter manual or complete manual) stores a snapshot of the
statements it contained under data/manual_snapshots/. A release letter compares the statements
that would be in the manual now (same stage) with such a snapshot and lists, per chapter and
question: new statements, changed wording, status changes and statements that dropped out.
"""
from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .manual_service import STAGES, STATUS_TEXT, ManualError, _cover, _finish, _Output
from .storage import now_iso, read_json, write_json_atomic

SNAPSHOT_RE = re.compile(r"(CH\d{2}|Gesamthandbuch)_[0-9-]+_Handbuch_(Draft|Reviewed|Released)")
STATUS_LABEL = {**STATUS_TEXT, "REJECTED": "abgelehnt"}
KINDS = ("new", "changed", "status", "removed")
KIND_LABEL = {"new": "Neu", "changed": "Geändert", "status": "Status geändert", "removed": "Entfallen"}


def snapshot_claims(claims: list[dict]) -> list[dict]:
    """The part of a statement a release letter compares."""
    return [{"claimId": c["claimId"], "chapterId": c["chapterId"], "questionId": c["questionId"],
             "statement": c["canonicalStatement"], "status": c["validationStatus"],
             "division": c.get("division", ""), "role": c.get("role", "")} for c in claims]


class SnapshotStore:
    def __init__(self, folder: Path):
        self.folder = Path(folder)

    def save(self, snapshot_id: str, *, kind: str, stage: str, chapters: list[str], design: str, files: list[str],
             claims: list[dict]) -> dict:
        if not SNAPSHOT_RE.fullmatch(snapshot_id):
            raise ValueError(f"invalid snapshot id {snapshot_id}")
        self.folder.mkdir(parents=True, exist_ok=True)
        record = {"snapshotId": snapshot_id, "kind": kind, "stage": stage, "chapters": chapters, "design": design,
                  "createdAt": now_iso(), "files": files, "claims": snapshot_claims(claims)}
        write_json_atomic(self.folder / f"{snapshot_id}.json", record)
        return record

    def list(self) -> list[dict]:
        out = []
        for path in self.folder.glob("*.json"):
            if not SNAPSHOT_RE.fullmatch(path.stem):
                continue
            try:
                record = read_json(path)
            except (OSError, json.JSONDecodeError):
                continue
            out.append({k: record.get(k) for k in ("snapshotId", "kind", "stage", "chapters", "design", "createdAt")}
                       | {"claims": len(record.get("claims", []))})
        return sorted(out, key=lambda r: r.get("createdAt") or "", reverse=True)

    def get(self, snapshot_id: str) -> dict:
        if not SNAPSHOT_RE.fullmatch(snapshot_id or "") or not (self.folder / f"{snapshot_id}.json").is_file():
            raise ManualError("Basis-Handbuchstand nicht gefunden.", 404)
        try:
            return read_json(self.folder / f"{snapshot_id}.json")
        except json.JSONDecodeError as exc:
            raise ManualError("Die gespeicherte Momentaufnahme ist beschädigt.", 500) from exc


def compare(before: list[dict], now: list[dict], all_claims: dict[str, dict]) -> list[dict]:
    """Changes from snapshot `before` to the current statements `now` (both in snapshot form).

    all_claims: every current claim by id, to say why a statement dropped out (rejected, below the stage, deleted)."""
    old = {c["claimId"]: c for c in before}
    new = {c["claimId"]: c for c in now}
    changes = []
    for claim_id, c in new.items():
        if claim_id not in old:
            changes.append({"kind": "new", **c})
            continue
        o = old[claim_id]
        if o["statement"] != c["statement"]:
            changes.append({"kind": "changed", **c, "before": o["statement"]})
        elif o["status"] != c["status"]:
            changes.append({"kind": "status", **c, "statusBefore": o["status"]})
    for claim_id, o in old.items():
        if claim_id in new:
            continue
        current = all_claims.get(claim_id)
        reason = (f"Status jetzt {STATUS_LABEL.get(current['validationStatus'], current['validationStatus'])}" if current
                  else "Aussage gelöscht (Import entfernt)")
        changes.append({"kind": "removed", **o, "reason": reason})
    return changes


def build_release_letter(snapshot: dict, stage: str, changes: list[dict], chapters: list[dict], design: dict, release: str = "") -> dict:
    """HTML, Word and Markdown release letter. chapters: the chapter configurations in scope, in chapter order."""
    from . import word_template as wt

    if stage not in STAGES:
        raise ManualError("Stufe muss Draft, Reviewed oder Released sein.", 400)
    release = " ".join(str(release or "").split())
    if len(release) > 40:
        raise ManualError("Der Release-Name darf höchstens 40 Zeichen lang sein.", 400)
    e = html.escape
    c = design["colors"]
    now = datetime.now(timezone.utc).astimezone()
    since = datetime.fromisoformat(snapshot["createdAt"].replace("Z", "+00:00")).astimezone()
    basis = f"{'Gesamthandbuch' if snapshot['kind'] == 'book' else snapshot['chapters'][0]} {snapshot['stage']} vom {since:%d.%m.%Y %H:%M}"
    title = f"{design['documentTitle']} – Release Letter"
    values = {"chapter": ", ".join(ch["chapterId"] for ch in chapters) if len(chapters) <= 3 else f"{len(chapters)} Kapitel",
              "chapterTitle": "Release Letter", "version": f"Release Letter {stage}", "date": f"{now:%d.%m.%Y}",
              "stage": stage, "release": release or f"{now:%d.%m.%Y}", "page": "", "pages": ""}
    counts = {k: sum(1 for ch in changes if ch["kind"] == k) for k in KINDS}
    meta = ([("Release", release)] if release else []) + [("Basis", basis), ("Vergleich mit", f"aktuellem Stand {stage}, {now:%d.%m.%Y %H:%M}"),
            ("Kapitel", ", ".join(ch["chapterId"] for ch in chapters) or "—"),
            ("Änderungen", " · ".join(f"{KIND_LABEL[k]} {counts[k]}" for k in KINDS)),
            ("Erstellt mit", "oneSCM360 Knowledge Studio"), ("Designvorlage", design["name"])]
    out = _Output()
    _cover(out, design, f"Änderungen seit {basis}", meta, {}, None, stage)
    out.md += [f"# {title}", "", f"**Basis:** {basis} · **Vergleich mit:** aktuellem Stand {stage}", "",
               "| Kapitel | " + " | ".join(KIND_LABEL[k] for k in KINDS) + " |", "|---|" + "---|" * len(KINDS)]

    by_chapter: dict[str, list] = {}
    for change in changes:
        by_chapter.setdefault(change["chapterId"], []).append(change)
    summary = [[ch["chapterId"], ch["title"]] + [str(sum(1 for x in by_chapter.get(ch["chapterId"], []) if x["kind"] == k)) for k in KINDS]
               for ch in chapters]
    header = ["Kapitel", "Titel"] + [KIND_LABEL[k] for k in KINDS]
    out.h += ["<h2>Übersicht</h2>", "<table><tr>" + "".join(f"<th>{e(x)}</th>" for x in header) + "</tr>"]
    out.h += ["<tr>" + "".join(f"<td>{e(x)}</td>" for x in row) + "</tr>" for row in summary] + ["</table>"]
    out.w += [wt.paragraph("Heading2", "Übersicht"), wt.table(header, summary, design, widths=[12, 36, 13, 13, 13, 13])]
    out.md += [f"| {row[0]} | " + " | ".join(row[2:]) + " |" for row in summary] + [""]
    if not changes:
        out.h.append('<p class="src">Seit der Basis gibt es keine Änderungen.</p>')
        out.w.append(wt.paragraph("Quellenzeile", "Seit der Basis gibt es keine Änderungen."))
        out.md += ["_Seit der Basis gibt es keine Änderungen._", ""]

    tag = {"new": ("NEU", c["ok"]), "changed": ("GEÄNDERT", c["petrol"]), "status": ("STATUS", c["info"]), "removed": ("ENTFALLEN", c["crit"])}
    badge_class = {"new": "b-ok", "changed": "b-both", "status": "b-open", "removed": "b-crit"}
    order = {k: i for i, k in enumerate(KINDS)}
    number = 0
    for chapter in chapters:
        items = by_chapter.get(chapter["chapterId"], [])
        if not items:
            continue
        number += 1
        heading = f"{number} Kapitel {chapter['chapterId'][2:]} – {chapter['title']}"
        titles = {q["questionId"]: q["title"] for q in chapter["questions"]}
        position = {q["questionId"]: i for i, q in enumerate(chapter["questions"])}
        out.h.append(f"<h1>{e(heading)}</h1>")
        out.w.append(wt.paragraph("Heading1", heading))
        out.md += [f"## {heading}", ""]
        question = None
        for item in sorted(items, key=lambda x: (position.get(x["questionId"], 99), order[x["kind"]])):
            if item["questionId"] != question:
                if question is not None:
                    out.h.append("</ul>")
                    out.md.append("")
                question = item["questionId"]
                label = f"{question} · {titles.get(question, '')}".rstrip(" ·")
                out.h.append(f"<h2>{e(label)}</h2><ul>")
                out.w.append(wt.paragraph("Heading2", label))
                out.md += [f"### {label}", ""]
            text, color = tag[item["kind"]]
            detail = ""
            if item["kind"] == "changed":
                detail = f"vorher: {item['before']}"
            elif item["kind"] == "status":
                detail = f"{STATUS_LABEL.get(item['statusBefore'], item['statusBefore'])} → {STATUS_LABEL.get(item['status'], item['status'])}"
            elif item["kind"] == "removed":
                detail = item["reason"]
            out.h.append(f'<li><span class="badge {badge_class[item["kind"]]}">{e(text)}</span> {e(item["statement"])}'
                         + (f' <span class="src">({e(detail)})</span>' if detail else "") + "</li>")
            out.w.append(wt.paragraph("ListBullet", "", wt.run(f"{text}  ", bold=True, color=color) + wt.run(item["statement"])
                                      + (wt.run(f"  ({detail})", color=c["muted"]) if detail else "")))
            out.md.append(f"- **{text}** {item['statement']}" + (f" _({detail})_" if detail else ""))
        out.h.append("</ul>")
        out.md.append("")
    page, docx, markdown = _finish(out, design, values, title, stage)
    return {"html": page, "docx": docx, "markdown": markdown, "title": title,
            "stats": {**counts, "total": len(changes), "chapters": [ch["chapterId"] for ch in chapters], "basis": basis,
                      "release": release, "design": design["name"]}}
