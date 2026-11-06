"""oneSCM360 icon set: consistent 24×24 outline icons drawn for this app (no third-party licence).

Every icon is a list of primitive shapes so that it can be rendered safely as SVG
on the server (downloads, manuals) and in the browser (DOM, no innerHTML).
Style: stroke 1.8, round caps and joins, colour via currentColor.
"""
from __future__ import annotations

import re

P, C, R, D = "path", "circle", "rect", "dot"

ICONS: dict[str, dict] = {
    # status & notes
    "info": {"label": "Info / Quellenbasis", "category": "Hinweise", "shapes": [(C, 12, 12, 9), (P, "M12 11v5"), (D, 12, 7.8)]},
    "lightbulb": {"label": "Tipp", "category": "Hinweise", "shapes": [
        (P, "M9 18h6"), (P, "M10 21h4"),
        (P, "M12 3a6 6 0 0 0-3.6 10.8c.7.6 1.1 1.3 1.1 2.2V16h5v0c0-.9.4-1.6 1.1-2.2A6 6 0 0 0 12 3z")]},
    "pending": {"label": "Offen / Validierung", "category": "Hinweise", "shapes": [
        (P, "M9 3.5h6v3H9z"), (P, "M15.5 5H18a1 1 0 0 1 1 1v4.5"), (P, "M8.5 5H6a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h5"),
        (C, 17, 17, 4.2), (P, "M17 15v2.2l1.4 1")]},
    "warning": {"label": "Achtung / Nicht Bestandteil", "category": "Hinweise", "shapes": [
        (P, "M10.3 4.2 2.6 18a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 4.2a2 2 0 0 0-3.4 0z"), (P, "M12 9.5v4.5"), (D, 12, 17.2)]},
    "report": {"label": "Konflikt", "category": "Hinweise", "shapes": [
        (P, "M8.2 3h7.6L21 8.2v7.6L15.8 21H8.2L3 15.8V8.2z"), (P, "M12 8v5"), (D, 12, 16.2)]},
    "verified": {"label": "Belegt", "category": "Hinweise", "shapes": [
        (P, "M12 3 4.5 6v5.6c0 4.4 3.1 8.2 7.5 9.4 4.4-1.2 7.5-5 7.5-9.4V6z"), (P, "m8.8 12.2 2.3 2.3 4.3-4.6")]},
    "toggle_off": {"label": "Nicht aktiviert", "category": "Hinweise", "shapes": [(R, 2, 7, 20, 10, 5), (C, 7, 12, 2.6)]},
    "check": {"label": "Erledigt", "category": "Hinweise", "shapes": [(C, 12, 12, 9), (P, "m8 12.3 2.8 2.8L16.2 9.6")]},
    "question": {"label": "Frage / FAQ", "category": "Hinweise", "shapes": [
        (C, 12, 12, 9), (P, "M9.6 9.3a2.5 2.5 0 1 1 3.6 2.3c-.7.3-1.2 1-1.2 1.8v.4"), (D, 12, 16.8)]},
    # roles & organisation
    "badge": {"label": "Rolle / Benutzer", "category": "Rollen & Organisation", "shapes": [
        (R, 5, 3, 14, 18, 2), (C, 12, 10, 2.6), (P, "M8.3 17.2c.7-1.9 2-2.9 3.7-2.9s3 1 3.7 2.9"), (P, "M10 6h4")]},
    "group": {"label": "Benutzergruppe", "category": "Rollen & Organisation", "shapes": [
        (C, 9, 8, 3.2), (P, "M3 20c.4-3.3 2.8-5.2 6-5.2s5.6 1.9 6 5.2"), (C, 17.2, 9, 2.4), (P, "M15.8 14.6c2.6.1 4.6 1.7 5.2 4.6")]},
    "dealer": {"label": "Händler / Standort", "category": "Rollen & Organisation", "shapes": [
        (P, "M3 10.5 12 4l9 6.5"), (P, "M5 9.5V20h14V9.5"), (P, "M10 20v-5h4v5")]},
    "headquarters": {"label": "HQ / Zentrale", "category": "Rollen & Organisation", "shapes": [
        (R, 4, 3, 10, 18, 1), (P, "M14 9h5a1 1 0 0 1 1 1v11"), (P, "M7.5 7h3M7.5 11h3M7.5 15h3"), (P, "M3 21h18")]},
    "market": {"label": "Markt / Land", "category": "Rollen & Organisation", "shapes": [
        (C, 12, 12, 9), (P, "M3 12h18"), (P, "M12 3c2.5 2.5 3.8 5.5 3.8 9s-1.3 6.5-3.8 9c-2.5-2.5-3.8-5.5-3.8-9S9.5 5.5 12 3z")]},
    "security": {"label": "Sicherheit / Berechtigung", "category": "Rollen & Organisation", "shapes": [
        (R, 5, 10.5, 14, 10.5, 2), (P, "M8 10.5V7.5a4 4 0 0 1 8 0v3"), (D, 12, 15.7)]},
    # systems & processes
    "hub": {"label": "System / Schnittstelle", "category": "Systeme & Prozesse", "shapes": [
        (C, 12, 12, 2.6), (C, 5, 5, 2), (C, 19, 5, 2), (C, 5, 19, 2), (C, 19, 19, 2),
        (P, "M10.1 10.1 6.4 6.4M13.9 10.1l3.7-3.7M10.1 13.9l-3.7 3.7M13.9 13.9l3.7 3.7")]},
    "process": {"label": "Prozess", "category": "Systeme & Prozesse", "shapes": [
        (R, 3, 4, 6, 5, 1), (R, 15, 4, 6, 5, 1), (R, 15, 15, 6, 5, 1), (P, "M9 6.5h6"), (P, "M12 6.5v11h3")]},
    "settings": {"label": "Einstellungen", "category": "Systeme & Prozesse", "shapes": [
        (P, "M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"), (C, 15, 6, 2), (C, 9, 12, 2), (C, 17, 18, 2)]},
    "search": {"label": "Suche", "category": "Systeme & Prozesse", "shapes": [(C, 10.5, 10.5, 6.5), (P, "m20 20-4.8-4.8")]},
    "link": {"label": "Verknüpfung", "category": "Systeme & Prozesse", "shapes": [
        (P, "M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"), (P, "M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1")]},
    "chart": {"label": "Auswertung / KPI", "category": "Systeme & Prozesse", "shapes": [(P, "M4 4v16h16"), (P, "M8.5 16v-5M12.5 16V8M16.5 16v-3")]},
    "calendar": {"label": "Termin / PI", "category": "Systeme & Prozesse", "shapes": [(R, 3, 5, 18, 16, 2), (P, "M3 10h18M8 3v4M16 3v4")]},
    "clock": {"label": "Zeit / Frist", "category": "Systeme & Prozesse", "shapes": [(C, 12, 12, 9), (P, "M12 7v5l3.2 2")]},
    "euro": {"label": "Preis / Finanzen", "category": "Systeme & Prozesse", "shapes": [
        (C, 12, 12, 9), (P, "M15.2 8.6a4.3 4.3 0 1 0 0 6.8"), (P, "M7.5 11h5.5M7.5 13.2h5.5")]},
    # documents & media
    "description": {"label": "Dokument", "category": "Dokumente & Medien", "shapes": [
        (P, "M6 3h8l4 4v14H6z"), (P, "M14 3v4h4"), (P, "M9 12h6M9 16h6")]},
    "release": {"label": "Release / Version", "category": "Dokumente & Medien", "shapes": [
        (P, "M3 12.5V4h8.5L21 13.5 13.5 21z"), (C, 7.8, 8.3, 1.5)]},
    "mail": {"label": "Release Letter / Mitteilung", "category": "Dokumente & Medien", "shapes": [(R, 3, 5, 18, 14, 2), (P, "m3.5 7 8.5 6 8.5-6")]},
    "training": {"label": "Training", "category": "Dokumente & Medien", "shapes": [(P, "M2 9.5 12 4.5l10 5-10 5z"), (P, "M6 11.5v4.5c2.5 2.2 9.5 2.2 12 0v-4.5"), (P, "M22 9.5v5")]},
    "screenshot": {"label": "Screenshot-Platzhalter", "category": "Dokumente & Medien", "shapes": [
        (R, 3, 4, 18, 13, 1.5), (P, "M8 21h8M12 17v4"), (P, "M6.5 9V7.5H8M17.5 12v1.5H16")]},
    "image": {"label": "Bild-Platzhalter", "category": "Dokumente & Medien", "shapes": [(R, 3, 4, 18, 16, 2), (C, 8.5, 9.5, 1.6), (P, "m21 15.5-5-5-9 9")]},
    "download": {"label": "Download", "category": "Dokumente & Medien", "shapes": [(P, "M12 4v11"), (P, "m7 10.5 5 5 5-5"), (P, "M5 20h14")]},
    # vehicles
    "car": {"label": "Sparte PC", "category": "Sparten", "shapes": [
        (P, "M3.5 16.5V12l2.2-5h12.6l2.2 5v4.5z"), (P, "M3.5 12h17"), (C, 7.5, 16.5, 1.8), (C, 16.5, 16.5, 1.8)]},
    "van": {"label": "Sparte Van", "category": "Sparten", "shapes": [
        (P, "M2.5 17V6.5h11.5l4.5 4.5h3V17z"), (P, "M14 6.5V11h4.5"), (C, 7, 17, 1.8), (C, 17.5, 17, 1.8)]},
}

_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


def icon_list() -> list[dict]:
    return [{"name": name, "label": icon["label"], "category": icon["category"],
             "shapes": [list(shape) for shape in icon["shapes"]]} for name, icon in ICONS.items()]


def svg(name: str, color: str = "#00708A", size: int = 24, symbol_id: str | None = None) -> str:
    """Return a standalone SVG (or a <symbol> when symbol_id is given) for a known icon."""
    if name not in ICONS:
        raise KeyError(name)
    if not _COLOR.match(color or ""):
        color = "#00708A"
    parts = []
    for shape in ICONS[name]["shapes"]:
        kind = shape[0]
        if kind == P:
            parts.append(f'<path d="{shape[1]}"/>')
        elif kind == C:
            parts.append(f'<circle cx="{shape[1]}" cy="{shape[2]}" r="{shape[3]}"/>')
        elif kind == R:
            parts.append(f'<rect x="{shape[1]}" y="{shape[2]}" width="{shape[3]}" height="{shape[4]}" rx="{shape[5]}"/>')
        elif kind == D:
            parts.append(f'<circle cx="{shape[1]}" cy="{shape[2]}" r="1.1" fill="currentColor" stroke="none"/>')
    body = "".join(parts)
    if symbol_id:  # inside HTML: colour follows the surrounding text colour
        attrs = 'fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"'
        return f'<symbol id="{symbol_id}" viewBox="0 0 24 24" {attrs}>{body}</symbol>'
    # standalone file (Word, PowerPoint): explicit colour, no currentColor
    body = body.replace("currentColor", color)
    attrs = f'fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" {attrs}>'
            f'<title>{ICONS[name]["label"]}</title>{body}</svg>')
