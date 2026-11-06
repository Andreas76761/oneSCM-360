"""HTML/HTM parser: returns text blocks and tables in document order."""
from __future__ import annotations

import re
from html.parser import HTMLParser

BLOCK_TAGS = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "section", "article",
              "header", "footer", "blockquote", "pre", "dt", "dd", "caption", "summary"}
SKIP_TAGS = {"script", "style", "noscript", "template", "head", "title"}


class ParseError(ValueError):
    """Raised when a document cannot be parsed into usable content."""


def decode_html(data: bytes) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="replace")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    head = data[:4096].decode("ascii", errors="ignore")
    match = re.search(r"charset=[\"']?([A-Za-z0-9_\-]+)", head, re.I)
    candidates = [match.group(1)] if match else []
    candidates += ["utf-8", "cp1252"]
    for enc in candidates:
        try:
            return data.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("utf-8", errors="replace")


def _clean(text: str) -> str:
    return re.sub(r"[ \t\r\f\v ]+", " ", text).strip()


class _Collector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: list[dict] = []
        self._buf: list[str] = []
        self._style = "para"
        self._skip = 0
        self._table_depth = 0
        self._rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._cell_header = False
        self._header_row = False

    # -- text flushing -------------------------------------------------
    def _flush(self):
        text = _clean("".join(self._buf))
        self._buf = []
        if text:
            for line in [l.strip() for l in text.split("\n")]:
                if line:
                    self.blocks.append({"kind": "text", "style": self._style, "text": line})
        self._style = "para"

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in SKIP_TAGS:
            self._skip += 1
            return
        if self._skip:
            return
        if tag == "table":
            if self._table_depth == 0:
                self._flush()
                self._rows = []
            elif self._cell is not None:
                self._cell.append(" ")
            self._table_depth += 1
            return
        if self._table_depth:
            if self._table_depth > 1:
                if self._cell is not None:
                    self._cell.append(" ")  # nested tables: text flows into the outer cell
                return
            if tag == "tr":
                self._row = []
                self._header_row = True
            elif tag in ("td", "th"):
                if self._row is None:
                    self._row = []
                    self._header_row = True
                self._cell = []
                self._cell_header = tag == "th"
            elif tag in ("br", "p", "div", "li") and self._cell is not None and self._cell:
                self._cell.append(" ")
            return
        if tag == "br":
            self._buf.append("\n")
        elif tag in BLOCK_TAGS:
            self._flush()
            if re.fullmatch(r"h[1-6]", tag):
                self._style = "heading"
            elif tag == "li":
                self._style = "list"

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
            return
        if self._skip:
            return
        if self._table_depth:
            if tag == "table":
                self._table_depth -= 1
                if self._table_depth == 0:
                    self._end_row()
                    rows = [r for r in self._rows if any(c for c, _ in r)]
                    if rows:
                        header_flags = [all(h for _, h in r) for r in rows]
                        self.blocks.append({
                            "kind": "table",
                            "hasHeader": header_flags[0],
                            "rows": [[c for c, _ in r] for r in rows],
                        })
                    self._rows = []
                return
            if self._table_depth > 1:
                return
            if tag in ("td", "th"):
                self._end_cell()
            elif tag == "tr":
                self._end_row()
            return
        if tag in BLOCK_TAGS:
            self._flush()

    def _end_cell(self):
        if self._cell is not None and self._row is not None:
            self._row.append((_clean("".join(self._cell)), self._cell_header))
        self._cell = None

    def _end_row(self):
        self._end_cell()
        if self._row:
            self._rows.append(self._row)
        self._row = None

    def handle_data(self, data):
        if self._skip:
            return
        if self._table_depth:
            if self._cell is not None:
                self._cell.append(data)
            return
        self._buf.append(data)

    def close(self):
        super().close()
        if self._table_depth:
            self._table_depth = 1
            self.handle_endtag("table")
        self._flush()


def parse_html(data: bytes) -> dict:
    text = decode_html(data)
    if "<" not in text:
        raise ParseError("Die Datei enthält kein HTML.")
    collector = _Collector()
    collector.feed(text)
    collector.close()
    return {"blocks": collector.blocks, "media": []}
