"""Design studio: variable design templates for manuals, release letters, quick references, trainings.

A template holds page setup, header/footer, fonts, typography per element, colour palette,
element switches and icon choices. Shipped templates (design_templates.json) are copied to
data/design_templates.json on first start; the user edits only that copy.
All values are validated against allow-lists, so a template can never inject CSS or markup.
"""
from __future__ import annotations

import copy
import html
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .icons import ICONS, svg
from .storage import LOCK, write_json_atomic

FONTS = ["Segoe UI", "Calibri", "Aptos", "Arial", "Verdana", "Tahoma", "Georgia", "Cambria", "Times New Roman"]
DOC_TYPES = {"handbuch": "Benutzerhandbuch", "releaseletter": "Release Letter", "quickreference": "Quick Reference",
             "training": "Trainingsunterlage", "other": "Sonstiges"}
COLORS = {  # key: label
    "navy": "Primär (Titel, H1, Tabellenkopf)", "petrol": "Akzent (H2, Linien, Icons)", "text": "Fließtext",
    "muted": "Text sekundär (Quellen, Beschriftung)", "line": "Linie / Tabellenrahmen", "soft": "Fläche hell (Zebra, Metadaten)",
    "onPrimary": "Schrift auf Primärfarbe", "placeholder": "Rahmen Platzhalter",
    "info": "Info", "infoBg": "Info Fläche", "ok": "Tipp / Belegt", "okBg": "Tipp / Belegt Fläche",
    "warn": "Offen / Warnung", "warnBg": "Offen / Warnung Fläche", "crit": "Kritisch / Konflikt", "critBg": "Kritisch / Konflikt Fläche",
    "off": "Nicht aktiviert", "offBg": "Nicht aktiviert Fläche", "pc": "Sparte PC", "van": "Sparte Van",
}
ELEMENTS = {  # key: label
    "title": "Deckblatt-Titel", "subtitle": "Deckblatt-Untertitel", "subtitleEn": "Untertitel EN", "h1": "Überschrift 1",
    "h2": "Überschrift 2", "h3": "Überschrift 3", "body": "Fließtext", "tableHead": "Tabellenkopf", "tableBody": "Tabelleninhalt",
    "box": "Hinweisbox", "caption": "Bildunterschrift", "source": "Quellenzeile", "badge": "Badges",
}
ICON_ROLES = {"info": "Info / Quellenbasis", "tip": "Tipp", "open": "Offen / Validierung", "warn": "Warnung / Nicht Bestandteil",
              "conflict": "Konflikt", "verified": "Belegt", "off": "Nicht aktiviert", "screenshot": "Screenshot-Platzhalter",
              "image": "Bild-Platzhalter", "role": "Rolle / Benutzer", "system": "System / Schnittstelle",
              "document": "Dokument", "process": "Prozess"}
PLACEHOLDERS = ["{chapter}", "{chapterTitle}", "{version}", "{date}", "{stage}", "{release}", "{page}", "{pages}"]
RATIOS = ["16:9", "4:3", "3:2", "1:1"]
WEIGHTS = [400, 600, 700]
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")


class DesignError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _num(value, low, high, label):
    try:
        number = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        raise DesignError(f"{label}: Zahl erwartet.")
    if not low <= number <= high:
        raise DesignError(f"{label}: erlaubt sind {low:g} bis {high:g}.")
    return round(number, 2)


def _text(value, limit, label, allow_empty=True):
    text = re.sub(r"\s+", " ", str(value or "")).strip()[:limit]
    if not text and not allow_empty:
        raise DesignError(f"{label} darf nicht leer sein.")
    for token in re.findall(r"\{[^}]*\}", text):
        if token not in PLACEHOLDERS:
            raise DesignError(f"{label}: unbekannter Platzhalter {token}. Erlaubt: {', '.join(PLACEHOLDERS)}")
    return text


def validate(template: dict) -> dict:
    """Normalise a template; raises DesignError on any invalid value."""
    if not isinstance(template, dict):
        raise DesignError("Ungültige Designvorlage.")
    t = {}
    t["name"] = _text(template.get("name"), 80, "Name", allow_empty=False)
    t["documentType"] = template.get("documentType") if template.get("documentType") in DOC_TYPES else "other"
    t["description"] = _text(template.get("description"), 300, "Beschreibung")
    t["documentTitle"] = _text(template.get("documentTitle") or t["name"], 80, "Dokumenttitel", allow_empty=False)
    page = template.get("page") or {}
    t["page"] = {"format": page.get("format") if page.get("format") in ("A4", "Letter") else "A4",
                 "orientation": page.get("orientation") if page.get("orientation") in ("portrait", "landscape") else "portrait",
                 "marginLeft": _num(page.get("marginLeft", 2.5), 0.5, 5, "Rand links (cm)"),
                 "marginRight": _num(page.get("marginRight", 2.5), 0.5, 5, "Rand rechts (cm)"),
                 "marginTop": _num(page.get("marginTop", 2.0), 0.5, 5, "Rand oben (cm)"),
                 "marginBottom": _num(page.get("marginBottom", 2.0), 0.5, 5, "Rand unten (cm)"),
                 "columns": int(_num(page.get("columns", 1), 1, 3, "Spalten"))}
    t["header"] = _text(template.get("header"), 140, "Kopfzeile")
    t["footer"] = _text(template.get("footer"), 140, "Fußzeile")
    fonts = template.get("fonts") or {}
    t["fonts"] = {key: fonts.get(key) if fonts.get(key) in FONTS else default
                  for key, default in (("heading", "Segoe UI"), ("body", "Calibri"))}
    colors = template.get("colors") or {}
    t["colors"] = {}
    for key, label in COLORS.items():
        value = colors.get(key, "")
        if not _HEX.match(str(value)):
            raise DesignError(f"Farbe „{label}“: HEX-Wert wie #0B2A4A erwartet.")
        t["colors"][key] = value.upper()
    typo = template.get("typography") or {}
    t["typography"] = {}
    for key, label in ELEMENTS.items():
        e = typo.get(key) or {}
        color = e.get("color", "text")
        if color not in COLORS:
            raise DesignError(f"{label}: unbekannte Farbe „{color}“.")
        weight = int(_num(e.get("weight", 400), 100, 900, f"{label} Schnitt"))
        t["typography"][key] = {"font": e.get("font") if e.get("font") in ("heading", "body") else "body",
                                "size": _num(e.get("size", 11), 6, 72, f"{label} Größe (pt)"),
                                "weight": min(WEIGHTS, key=lambda w: abs(w - weight)),
                                "italic": bool(e.get("italic", False)), "uppercase": bool(e.get("uppercase", False)),
                                "lineHeight": _num(e.get("lineHeight", 1.3), 0.8, 3, f"{label} Zeilenabstand"),
                                "before": _num(e.get("before", 0), 0, 72, f"{label} Abstand vor (pt)"),
                                "after": _num(e.get("after", 0), 0, 72, f"{label} Abstand nach (pt)"), "color": color}
    el = template.get("elements") or {}
    t["elements"] = {"h1Rule": bool(el.get("h1Rule", True)), "tableZebra": bool(el.get("tableZebra", True)),
                     "tableHeadBg": el.get("tableHeadBg") if el.get("tableHeadBg") in COLORS else "navy",
                     "boxBorder": _num(el.get("boxBorder", 4), 0, 12, "Rahmen Hinweisbox (px)"),
                     "badgeRadius": _num(el.get("badgeRadius", 10), 0, 20, "Rundung Badges (px)"),
                     "cellPaddingV": _num(el.get("cellPaddingV", 4), 0, 20, "Zellinnenrand oben/unten (pt)"),
                     "cellPaddingH": _num(el.get("cellPaddingH", 6), 0, 20, "Zellinnenrand links/rechts (pt)"),
                     "placeholderRatio": el.get("placeholderRatio") if el.get("placeholderRatio") in RATIOS else "16:9",
                     "imageRatio": el.get("imageRatio") if el.get("imageRatio") in RATIOS else "4:3",
                     "showSourceLines": bool(el.get("showSourceLines", True))}
    icons = template.get("icons") or {}
    t["icons"] = {}
    for role in ICON_ROLES:
        name = icons.get(role)
        if name not in ICONS:
            raise DesignError(f"Icon für „{ICON_ROLES[role]}“: unbekanntes Icon „{name}“.")
        t["icons"][role] = name
    t["iconColor"] = template.get("iconColor") if template.get("iconColor") in COLORS else "petrol"
    t["iconSize"] = _num(template.get("iconSize", 14), 8, 32, "Icongröße (pt)")
    return t


class DesignService:
    def __init__(self, shipped_path: Path, data_path: Path, backup_dir: Path):
        self.shipped_path = Path(shipped_path)
        self.path = Path(data_path)
        self.backup_dir = Path(backup_dir)
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.shipped_path, self.path)

    def _read(self, path=None) -> dict:
        try:
            data = json.loads(Path(path or self.path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise DesignError("Die Designvorlagen sind beschädigt. Sicherungen liegen unter data/backups.", 500) from exc
        if not isinstance(data.get("templates"), list):
            raise DesignError("Die Designvorlagen sind beschädigt.", 500)
        return data

    def _write(self, data: dict):
        if self.path.exists():
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
            shutil.copy2(self.path, self.backup_dir / f"design-{stamp}.json")
            for old in sorted(self.backup_dir.glob("design-*.json"))[:-30]:
                old.unlink(missing_ok=True)
        write_json_atomic(self.path, data)

    def shipped_ids(self) -> list[str]:
        return [t["id"] for t in self._read(self.shipped_path)["templates"]]

    def list(self) -> list[dict]:
        shipped = set(self.shipped_ids())
        return [{**t, "shipped": t["id"] in shipped} for t in self._read()["templates"]]

    def get(self, template_id: str) -> dict:
        found = next((t for t in self.list() if t["id"] == template_id), None)
        if not found:
            raise DesignError("Designvorlage nicht gefunden.", 404)
        return found

    def default_for(self, document_type: str = "handbuch") -> dict:
        templates = self.list()
        return next((t for t in templates if t["documentType"] == document_type), templates[0])

    def create(self, base_id: str, name: str) -> dict:
        base = self.get(base_id)
        with LOCK:
            data = self._read()
            slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")).strip("-")[:30] or "vorlage"
            new_id, n = slug, 1
            while any(t["id"] == new_id for t in data["templates"]) or not _ID.match(new_id):
                n += 1
                new_id = f"{slug}-{n}"[:40] if _ID.match(f"{slug}-{n}") else f"vorlage-{n}"
            template = {"id": new_id, **validate({**base, "name": name or f"{base['name']} (Kopie)"})}
            data["templates"].append(template)
            self._write(data)
        return self.get(new_id)

    def update(self, template_id: str, payload: dict) -> dict:
        clean = validate(payload)
        with LOCK:
            data = self._read()
            for index, template in enumerate(data["templates"]):
                if template["id"] == template_id:
                    data["templates"][index] = {"id": template_id, **clean}
                    self._write(data)
                    return self.get(template_id)
        raise DesignError("Designvorlage nicht gefunden.", 404)

    def delete(self, template_id: str):
        with LOCK:
            data = self._read()
            remaining = [t for t in data["templates"] if t["id"] != template_id]
            if len(remaining) == len(data["templates"]):
                raise DesignError("Designvorlage nicht gefunden.", 404)
            if not remaining:
                raise DesignError("Die letzte Designvorlage kann nicht gelöscht werden.")
            data["templates"] = remaining
            self._write(data)

    def reset(self, template_id: str) -> dict:
        shipped = next((t for t in self._read(self.shipped_path)["templates"] if t["id"] == template_id), None)
        if not shipped:
            raise DesignError("Nur ausgelieferte Vorlagen lassen sich zurücksetzen.")
        with LOCK:
            data = self._read()
            data["templates"] = [copy.deepcopy(shipped) if t["id"] == template_id else t for t in data["templates"]]
            if not any(t["id"] == template_id for t in data["templates"]):
                data["templates"].append(copy.deepcopy(shipped))
            self._write(data)
        return self.get(template_id)

    def import_template(self, payload: dict) -> dict:
        clean = validate(payload)
        created = self.create(self.list()[0]["id"], clean["name"])
        return self.update(created["id"], clean)


# ------------------------------------------------------------------------------------- rendering
def fill(text: str, values: dict) -> str:
    for key, value in values.items():
        text = text.replace("{" + key + "}", str(value))
    return text


def fill_without_pages(text: str, values: dict) -> str:
    """For HTML output: drop the "|"-separated parts that contain page numbers (only Word and print know them)."""
    parts = [part.strip() for part in text.split("|") if "{page}" not in part and "{pages}" not in part]
    return fill(" | ".join(p for p in parts if p), values)


def css(t: dict) -> str:
    """CSS for HTML output of a template (preview, pattern page, manuals). All values are validated."""
    c, f, ty, el, pg = t["colors"], t["fonts"], t["typography"], t["elements"], t["page"]
    rules = [":root{" + ";".join(f"--{k}:{v}" for k, v in c.items()) + "}",
             "*{box-sizing:border-box}",
             f"body{{margin:0;background:#E9EDF1;color:var(--text);font-family:'{f['body']}',Arial,sans-serif}}",
             f".page{{max-width:{'297mm' if pg['orientation'] == 'landscape' else '210mm'};margin:24px auto;background:#fff;"
             f"padding:{pg['marginTop']}cm {pg['marginRight']}cm {pg['marginBottom']}cm {pg['marginLeft']}cm;box-shadow:0 2px 12px rgba(0,0,0,.08)}}",
             f".cols{{column-count:{pg['columns']};column-gap:1cm}}"]

    def typo(selector, key, extra=""):
        e = ty[key]
        family = f["heading"] if e["font"] == "heading" else f["body"]
        rules.append(f"{selector}{{font-family:'{family}',Arial,sans-serif;font-size:{e['size']}pt;font-weight:{e['weight']};"
                     f"font-style:{'italic' if e['italic'] else 'normal'};line-height:{e['lineHeight']};"
                     f"margin:{e['before']}pt 0 {e['after']}pt;color:var(--{e['color']});"
                     f"{'text-transform:uppercase;letter-spacing:.03em;' if e['uppercase'] else ''}{extra}}}")
    typo(".title", "title")
    typo(".subtitle", "subtitle")
    typo(".subtitle-en", "subtitleEn")
    typo("h1", "h1", f"padding-bottom:4pt;{'border-bottom:2px solid var(--petrol);' if el['h1Rule'] else ''}")
    typo("h2", "h2")
    typo("h3", "h3")
    typo("p,li", "body")
    typo(".src", "source")
    typo(".cap", "caption")
    th, tb = ty["tableHead"], ty["tableBody"]
    pad = f"{el['cellPaddingV']}pt {el['cellPaddingH']}pt"
    rules += [
        "ul{margin:0 0 8pt;padding-left:18pt}",
        f"table{{width:100%;border-collapse:collapse;margin:6pt 0 4pt;break-inside:avoid}}",
        f"th{{background:var(--{el['tableHeadBg']});color:var(--{th['color']});text-align:left;padding:{pad};"
        f"font-family:'{f['heading'] if th['font'] == 'heading' else f['body']}',Arial,sans-serif;font-size:{th['size']}pt;"
        f"font-weight:{th['weight']};line-height:{th['lineHeight']}}}",
        f"td{{border-bottom:1px solid var(--line);padding:{pad};vertical-align:top;font-size:{tb['size']}pt;"
        f"line-height:{tb['lineHeight']};color:var(--{tb['color']})}}",
        "tr:nth-child(even) td{background:var(--soft)}" if el["tableZebra"] else "",
        "table.meta td:first-child{font-weight:700;width:32%;background:var(--soft)}",
    ]
    bx = ty["box"]
    rules += [
        f".box{{display:flex;gap:10px;padding:8pt 10pt;border-left:{el['boxBorder']}px solid;border-radius:4px;margin:{bx['before']}pt 0 {bx['after']}pt;"
        f"font-size:{bx['size']}pt;line-height:{bx['lineHeight']};break-inside:avoid}}",
        f".box svg{{flex:0 0 {t['iconSize']}pt;width:{t['iconSize']}pt;height:{t['iconSize']}pt;margin-top:2px}}",
        ".box p{margin:0;font-size:inherit}",
        ".info{background:var(--infoBg);border-color:var(--info)}.info svg{color:var(--info)}",
        ".tip{background:var(--okBg);border-color:var(--ok)}.tip svg{color:var(--ok)}",
        ".warn{background:var(--warnBg);border-color:var(--warn)}.warn svg{color:var(--warn)}",
        ".crit{background:var(--critBg);border-color:var(--crit)}.crit svg{color:var(--crit)}",
    ]
    bd = ty["badge"]
    rules += [
        f".badge{{display:inline-block;font-size:{bd['size']}pt;font-weight:{bd['weight']};letter-spacing:.03em;padding:1pt 6pt;"
        f"border-radius:{el['badgeRadius']}px;{'text-transform:uppercase;' if bd['uppercase'] else ''}vertical-align:1px}}",
        ".b-ok{background:var(--okBg);color:var(--ok)}.b-open{background:var(--warnBg);color:var(--warn)}",
        ".b-off{background:var(--offBg);color:var(--off)}.b-crit{background:var(--critBg);color:var(--crit)}",
        ".b-pc{background:var(--soft);color:var(--pc);box-shadow:inset 0 0 0 1px var(--pc)}",
        ".b-van{background:var(--soft);color:var(--van);box-shadow:inset 0 0 0 1px var(--van)}",
        ".b-both{background:var(--soft);color:var(--navy)}",
        ".ph{border:1.5px dashed var(--placeholder);background:var(--soft);border-radius:6px;display:flex;flex-direction:column;"
        "align-items:center;justify-content:center;color:var(--muted);font-size:10pt;text-align:center;margin:8pt 0 4pt;padding:12px}",
        f".ph svg{{width:40px;height:40px;color:var(--{t['iconColor']});margin-bottom:6px}}.ph strong{{color:var(--navy)}}",
        f".r-shot{{aspect-ratio:{el['placeholderRatio'].replace(':', '/')}}}",
        f".r-img{{aspect-ratio:{el['imageRatio'].replace(':', '/')};max-width:70%;margin-left:auto;margin-right:auto}}",
        ".swatches{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px}",
        ".sw{border:1px solid var(--line);border-radius:4px;overflow:hidden;font-size:8.5pt}.sw i{display:block;height:36px}.sw span{display:block;padding:3px 6px}",
        f".callout{{display:inline-flex;width:18px;height:18px;border-radius:50%;background:var(--{t['iconColor']});color:#fff;font-size:8.5pt;"
        "font-weight:700;align-items:center;justify-content:center}",
        f".hf{{display:flex;justify-content:space-between;font-size:{ty['source']['size']}pt;color:var(--muted);border-top:1px solid var(--line);"
        "padding-top:4pt;margin-top:18pt}",
        ".hf.top{border:none;margin:0 0 18pt;padding:0}",
        ".icons{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px}",
        ".ic{display:flex;flex-direction:column;align-items:center;gap:4px;border:1px solid var(--line);border-radius:6px;padding:8px;font-size:8.5pt;color:var(--muted);text-align:center}",
        f".ic svg{{width:28px;height:28px;color:var(--{t['iconColor']})}}",
        "@media print{body{background:#fff}.page{box-shadow:none;margin:0;max-width:none}}",
    ]
    rules += [f".sw-{k} i{{background:var(--{k})}}" for k in COLORS]
    return "\n".join(r for r in rules if r)


def symbols(t: dict) -> str:
    names = sorted(set(t["icons"].values()))
    return '<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>' + \
        "".join(svg(n, symbol_id=f"i-{n}") for n in names) + "</defs></svg>"


def icon_use(t: dict, role: str) -> str:
    return f'<svg aria-hidden="true"><use href="#i-{t["icons"][role]}"/></svg>'


def pattern_html(t: dict) -> str:
    """The design pattern page (like oneSCM_DesignPattern.html) generated from a template."""
    e = html.escape
    values = {"chapter": "XX", "chapterTitle": "Kapiteltitel", "version": "V.X", "date": "TT.MM.JJJJ", "stage": "Draft",
              "release": "R.X", "page": "X", "pages": "Y"}
    ty = t["typography"]
    font_label = lambda k: f"{t['fonts'][ty[k]['font']]} {ty[k]['size']:g} pt"
    swatches = "".join(f'<div class="sw sw-{k}"><i></i><span>{e(label)}<br>{v}</span></div>' for k, (label, v) in
                       ((k, (COLORS[k], t["colors"][k])) for k in COLORS))
    icon_cells = "".join(f'<div class="ic">{icon_use({"icons": {r: n}}, r)}<span>{e(ICON_ROLES[r])}<br><code>{n}</code></span></div>'
                         for r, n in t["icons"].items())
    return f"""<!doctype html><html lang="de"><head><meta charset="utf-8"><title>{e(t['documentTitle'])} – Design-Pattern</title>
<style>{css(t)}</style></head><body>{symbols(t)}
<div class="page">
<div class="hf top"><span>{e(fill(t['header'], values))}</span><span>Design-Pattern · {e(t['name'])}</span></div>
<p class="title">{e(t['documentTitle'])}</p>
<p class="subtitle">Kapitel XX – Kapiteltitel</p>
<p class="subtitle-en">English Chapter Title</p>
<table class="meta">
<tr><td>Version</td><td>V.X (X.0)</td></tr><tr><td>Stand</td><td>TT.MM.JJJJ</td></tr>
<tr><td>Status</td><td><span class="badge b-open">Entwurf – fachliche Validierung erforderlich</span></td></tr>
<tr><td>Verantwortlich</td><td>Name</td></tr><tr><td>Erstellt mit</td><td>oneSCM360 Knowledge Studio</td></tr>
<tr><td>Sprache</td><td>Deutsch</td></tr></table>
<div class="box info">{icon_use(t, 'info')}<p><strong>Hinweis zur Quellenbasis:</strong> Text der Hinweisbox (Info).</p></div>
<div class="cols">
<h1>1 Typografie</h1>
<h2>1.1 Überschrift 2 – {e(font_label('h2'))}</h2>
<h3>Überschrift 3 – {e(font_label('h3'))}</h3>
<p>Fließtext – {e(font_label('body'))}, Zeilenabstand {ty['body']['lineHeight']:g}, Abstand nach {ty['body']['after']:g} pt.
<strong>Hervorhebung fett</strong>, <em>Begriff kursiv</em>.</p>
<ul><li>Aufzählungspunkt eins,</li><li>Aufzählungspunkt zwei.</li></ul>
<h1>2 Tabellen</h1>
<table><tr><th>Bereich</th><th>Zweck</th><th>Hauptrolle</th><th>Sparte</th></tr>
<tr><td><strong>Contract Calculation</strong></td><td>Produkte anlegen, Preise und Gruppen zuordnen.</td><td>MPC</td><td><span class="badge b-both">beide</span></td></tr>
<tr><td><strong>Contract Management</strong></td><td>Aktive Verträge einsehen und Status ändern.</td><td>„Power User“ <span class="badge b-open">Offen</span></td><td><span class="badge b-pc">PC</span></td></tr>
<tr><td><strong>Revenue Management</strong></td><td>Rechnungen und Gutschriften erstellen.</td><td>Market Operation</td><td><span class="badge b-van">Van</span></td></tr></table>
<p class="src">Quellen: ONESCM-77, -78, -593</p>
<h1>3 Kennzeichnungen &amp; Badges</h1>
<p><span class="badge b-ok">Belegt</span> <span class="badge b-open">Offen – Validierung erforderlich</span> <span class="badge b-off">Nicht aktiviert</span>
<span class="badge b-crit">Konflikt</span> <span class="badge b-pc">PC</span> <span class="badge b-van">Van</span> <span class="badge b-both">beide</span> <span class="badge b-off">unklar</span></p>
<h1>4 Hinweisboxen</h1>
<div class="box info">{icon_use(t, 'info')}<p><strong>Info:</strong> Allgemeiner Hinweis.</p></div>
<div class="box tip">{icon_use(t, 'tip')}<p><strong>Tipp:</strong> In Word mit Rechtsklick → „Felder aktualisieren“ (F9).</p></div>
<div class="box warn">{icon_use(t, 'open')}<p><strong>[OFFEN – VALIDIERUNG ERFORDERLICH]</strong> Information muss vom Fachbereich bestätigt werden.</p></div>
<div class="box crit">{icon_use(t, 'warn')}<p><strong>Nicht Bestandteil von oneSCM:</strong> Abgrenzung / Konflikt.</p></div>
<h1>5 Platzhalter für Screens &amp; Bilder</h1>
<div class="ph r-shot">{icon_use(t, 'screenshot')}<strong>SCREENSHOT</strong>[Maske / Bereich] · {t['elements']['placeholderRatio']} · volle Textbreite</div>
<p class="cap">Abbildung 1.1 – [Titel] · Rolle: [MPC / MO / Dealer] · Sparte: [PC / Van]</p>
<table><tr><th>Nr.</th><th>Element im Screen</th><th>Beschreibung</th></tr>
<tr><td><span class="callout">1</span></td><td>[Feld / Button]</td><td>[Funktion]</td></tr>
<tr><td><span class="callout">2</span></td><td>[Feld / Button]</td><td>[Funktion]</td></tr></table>
<div class="ph r-img">{icon_use(t, 'image')}<strong>BILD / DIAGRAMM</strong>[Prozess / Systemübersicht] · {t['elements']['imageRatio']}</div>
<p class="cap">Abbildung 1.2 – [Titel]</p>
<h1>6 Farbpalette</h1>
<div class="swatches">{swatches}</div>
<h1>7 Icons</h1>
<div class="icons">{icon_cells}</div>
</div>
<div class="hf"><span>{e(fill(t['footer'], values))}</span><span>Seite: {t['page']['format']} {('quer' if t['page']['orientation'] == 'landscape' else 'hoch')}, Ränder {t['page']['marginLeft']:g}/{t['page']['marginRight']:g}/{t['page']['marginTop']:g}/{t['page']['marginBottom']:g} cm</span></div>
</div></body></html>"""
