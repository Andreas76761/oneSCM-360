"""Test helpers: temporary app instance and a minimal DOCX builder."""
from __future__ import annotations

import io
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402

H = {"X-oneSCM360": "1"}


class AppCase:
    """Mixin creating an isolated app with its own data, rules and OneDrive folder."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="onescm360-test-"))
        self.onedrive = self.tmp / "OneDrive - Test (tenant.onmicrosoft.com)" / "-oneSCM360"
        self.onedrive.mkdir(parents=True)
        self.rules_path = self.tmp / "rules.json"
        shutil.copy(ROOT / "rules.json", self.rules_path)
        self.app = create_app({"DATA_DIR": self.tmp / "data", "RULES_PATH": self.rules_path,
                               "ONEDRIVE_ROOT": str(self.onedrive)})
        self.client = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def services(self):
        return self.app.extensions["onescm"]

    def upload(self, content: bytes, name: str, chapter="CH01", language="DE", source="ROVO", force=False):
        data = {"file": (io.BytesIO(content), name), "chapterId": chapter, "language": language, "sourceType": source}
        if force:
            data["force"] = "1"
        return self.client.post("/api/import", data=data, headers=H, content_type="multipart/form-data")

    def post(self, url, payload):
        return self.client.post(url, json=payload, headers=H)

    def put(self, url, payload):
        return self.client.put(url, json=payload, headers=H)

    def delete(self, url):
        return self.client.delete(url, headers=H)


def html_doc(*parts: str) -> bytes:
    return ("<!doctype html><html><head><meta charset='utf-8'><title>t</title><style>p{}</style></head><body>"
            + "".join(parts) + "</body></html>").encode("utf-8")


def p(text: str) -> str:
    return f"<p>{escape(text)}</p>"


def html_table(rows, header=True) -> str:
    out = ["<table>"]
    for i, row in enumerate(rows):
        tag = "th" if header and i == 0 else "td"
        out.append("<tr>" + "".join(f"<{tag}>{escape(c)}</{tag}>" for c in row) + "</tr>")
    out.append("</table>")
    return "".join(out)


def make_docx(blocks, media: dict[str, bytes] | None = None) -> bytes:
    """blocks: list of str (paragraph), ("h", str) heading, or list-of-rows (table)."""
    body = []
    for block in blocks:
        if isinstance(block, str):
            body.append(f"<w:p><w:r><w:t xml:space=\"preserve\">{escape(block)}</w:t></w:r></w:p>")
        elif isinstance(block, tuple) and block[0] == "h":
            body.append(f"<w:p><w:pPr><w:pStyle w:val=\"Heading1\"/></w:pPr><w:r><w:t>{escape(block[1])}</w:t></w:r></w:p>")
        else:
            rows = []
            for i, row in enumerate(block):
                trpr = "<w:trPr><w:tblHeader/></w:trPr>" if i == 0 else ""
                cells = "".join(f"<w:tc><w:p><w:r><w:t>{escape(c)}</w:t></w:r></w:p></w:tc>" for c in row)
                rows.append(f"<w:tr>{trpr}{cells}</w:tr>")
            body.append("<w:tbl>" + "".join(rows) + "</w:tbl>")
    document = ("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
                "<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\"><w:body>"
                + "".join(body) + "<w:sectPr/></w:body></w:document>")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<?xml version=\"1.0\"?><Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
                         "<Default Extension=\"xml\" ContentType=\"application/xml\"/></Types>")
        archive.writestr("word/document.xml", document)
        for name, data in (media or {}).items():
            archive.writestr(f"word/media/{name}", data)
    return buffer.getvalue()


CH01_HTML = html_doc(
    "<h1>Kapitel 01</h1>",
    html_table([["Vorab", "Tabelle"], ["vor", "Frage"]]),
    p("01-F01: Was ist das Ziel?"),
    p("onescm unterstützt den Dealer bei Aufträgen für Passenger Car und VAN."),
    p("F04 Rollen"),
    p("Der Dealer darf Aufträge stornieren."),
    html_table([["Rolle", "Recht", "Größe"], ["Dealer", "Bestellen", "groß"], ["Market Operations", "Genehmigen"]]),
    p("01 F17"),
    p("Die Funktion ist seit PI16 produktiv (ONESCM-123)."),
    p("01-F18"),
    p("In PI17 ist möglicherweise eine Erweiterung geplant."),
)
