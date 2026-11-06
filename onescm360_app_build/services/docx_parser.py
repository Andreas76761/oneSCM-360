"""DOCX parser based on zipfile + ElementTree (no python-docx dependency).

Returns paragraphs and tables in document order plus embedded media files.
"""
from __future__ import annotations

import io
import re
import zipfile
import xml.etree.ElementTree as ET

from .html_parser import ParseError

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MAX_XML_BYTES = 200 * 1024 * 1024
MAX_MEDIA_BYTES = 200 * 1024 * 1024
MEDIA_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".emf", ".wmf", ".svg", ".webp"}


def _para_text(p) -> str:
    parts = []
    for node in p.iter():
        if node.tag == W + "t":
            parts.append(node.text or "")
        elif node.tag == W + "tab":
            parts.append("\t")
        elif node.tag in (W + "br", W + "cr"):
            parts.append("\n")
    return "".join(parts)


def _para_style(p) -> str:
    ppr = p.find(W + "pPr")
    if ppr is None:
        return "para"
    style = ppr.find(W + "pStyle")
    val = (style.get(W + "val") if style is not None else "") or ""
    if re.search(r"heading|berschrift|title|titel", val, re.I):
        return "heading"
    if ppr.find(W + "numPr") is not None or re.search(r"list", val, re.I):
        return "list"
    return "para"


def _cell_text(tc) -> str:
    texts = []
    for p in tc.iter(W + "p"):
        t = _para_text(p).strip()
        if t:
            texts.append(t)
    return re.sub(r"\s+", " ", " ".join(texts)).strip()


def _table(tbl) -> dict | None:
    rows = []
    header = False
    for i, tr in enumerate(tbl.findall(W + "tr")):
        trpr = tr.find(W + "trPr")
        if i == 0 and trpr is not None and trpr.find(W + "tblHeader") is not None:
            header = True
        cells = []
        for tc in tr.findall(W + "tc"):
            cells.append(_cell_text(tc))
            tcpr = tc.find(W + "tcPr")
            span = tcpr.find(W + "gridSpan") if tcpr is not None else None
            if span is not None:
                try:
                    cells.extend([""] * (int(span.get(W + "val", "1")) - 1))
                except ValueError:
                    pass
        if any(cells):
            rows.append(cells)
    if not rows:
        return None
    if not header and len(rows) > 1:
        # Heuristic: first row counts as header when it is fully filled text.
        header = all(c and not re.fullmatch(r"[\d.,\s%€-]+", c) for c in rows[0])
    return {"kind": "table", "hasHeader": header, "rows": rows}


def _walk(container, blocks):
    for child in container:
        if child.tag == W + "p":
            style = _para_style(child)
            for line in _para_text(child).split("\n"):
                line = re.sub(r"[ \t ]+", " ", line).strip()
                if line:
                    blocks.append({"kind": "text", "style": style, "text": line})
        elif child.tag == W + "tbl":
            table = _table(child)
            if table:
                blocks.append(table)
        elif child.tag == W + "sdt":
            content = child.find(W + "sdtContent")
            if content is not None:
                _walk(content, blocks)


def parse_docx(data: bytes) -> dict:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, ValueError) as exc:
        raise ParseError("Die DOCX-Datei ist beschädigt oder kein Word-Dokument.") from exc
    with archive:
        names = set(archive.namelist())
        if "word/document.xml" not in names:
            raise ParseError("Die DOCX-Datei ist beschädigt: word/document.xml fehlt.")
        info = archive.getinfo("word/document.xml")
        if info.file_size > MAX_XML_BYTES:
            raise ParseError("Der Dokumentinhalt ist zu groß.")
        try:
            root = ET.fromstring(archive.read("word/document.xml"))
        except (ET.ParseError, zipfile.BadZipFile, OSError, RuntimeError) as exc:
            raise ParseError("Die DOCX-Datei ist beschädigt: Dokument-XML nicht lesbar.") from exc
        body = root.find(W + "body")
        if body is None:
            raise ParseError("Die DOCX-Datei enthält keinen Dokumentkörper.")
        blocks: list[dict] = []
        _walk(body, blocks)
        media = []
        total = 0
        for name in sorted(names):
            if not name.startswith("word/media/"):
                continue
            ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
            if ext not in MEDIA_EXT:
                continue
            size = archive.getinfo(name).file_size
            total += size
            if total > MAX_MEDIA_BYTES:
                break
            try:
                media.append({"name": name.rsplit("/", 1)[-1], "data": archive.read(name)})
            except (zipfile.BadZipFile, OSError, RuntimeError):
                continue
    return {"blocks": blocks, "media": media}
