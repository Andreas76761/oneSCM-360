"""CommonMark/GFM tables to editable Word, without executing HTML or fetching assets."""
import io
import re
import zipfile
from html import escape
from pathlib import PurePath

from markdown_it import MarkdownIt

PARSER = MarkdownIt("commonmark", {"html": False}).enable("table").enable("strikethrough")


def tokens(text):
    from app import clean_text
    return PARSER.parse(clean_text(text, "Markdown", 1_000_000))


def inline_word(paragraph, items):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    bold = italic = strike = 0
    link = None
    for t in items or []:
        if t.type == "strong_open": bold += 1
        elif t.type == "strong_close": bold -= 1
        elif t.type == "em_open": italic += 1
        elif t.type == "em_close": italic -= 1
        elif t.type == "s_open": strike += 1
        elif t.type == "s_close": strike -= 1
        elif t.type == "link_open": link = t.attrGet("href")
        elif t.type == "link_close": link = None
        elif t.type in ["softbreak", "hardbreak"]: paragraph.add_run().add_break()
        elif t.type in ["text", "code_inline", "image", "html_inline"]:
            text = ("[Bild: " + t.content + " – lokale Medienzuordnung erforderlich]") if t.type == "image" else t.content
            run = paragraph.add_run(text)
            run.bold, run.italic, run.font.strike = bool(bold), bool(italic), bool(strike)
            if t.type == "code_inline": run.font.name = "Consolas"
            if link and re.match(r"^(https?://|mailto:)", link, re.I):
                rel = paragraph.part.relate_to(link, RT.HYPERLINK, is_external=True)
                element = OxmlElement("w:hyperlink"); element.set(qn("r:id"), rel)
                run._r.getparent().remove(run._r); element.append(run._r); paragraph._p.append(element)


def append_word(doc, text, heading_offset=0):
    from docx.shared import Inches, Pt
    from docx.oxml import OxmlElement
    rows = tokens(text)
    lists, quotes, pending_prefix = [], 0, None
    heading, paragraph, table, table_row, cell = None, None, None, None, None
    for index, t in enumerate(rows):
        if t.type == "heading_open": heading = min(9, int(t.tag[1:]) + heading_offset)
        elif t.type == "heading_close": heading = None; paragraph = None
        elif t.type in ["bullet_list_open", "ordered_list_open"]:
            lists.append({"ordered": t.type == "ordered_list_open", "next": int(t.attrGet("start") or 1)})
        elif t.type in ["bullet_list_close", "ordered_list_close"]: lists.pop()
        elif t.type == "list_item_open":
            entry = lists[-1]; pending_prefix = str(entry["next"])+". " if entry["ordered"] else "• "
            entry["next"] += 1
        elif t.type == "list_item_close": pending_prefix = None
        elif t.type == "blockquote_open": quotes += 1
        elif t.type == "blockquote_close": quotes -= 1
        elif t.type == "table_open":
            table = doc.add_table(rows=0, cols=0)
            if "Table Grid" in doc.styles: table.style = "Table Grid"
        elif t.type == "table_close": table = None
        elif t.type == "tr_open": table_row = None; cell = None
        elif t.type in ["th_open", "td_open"]:
            if table_row is None:
                # The first row determines the table column count.
                if not table.columns:
                    n = 0
                    for token in rows[index:]:
                        if token.type == "tr_close": break
                        n += token.type in ["th_open", "td_open"]
                    section = doc.sections[-1]
                    available = section.page_width - section.left_margin - section.right_margin
                    for _ in range(n): table.add_column(int(available / max(n,1)))
                table_row = table.add_row(); cell = 0
                if t.type == "th_open":
                    table_row._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))
            else: cell += 1
            paragraph = table_row.cells[cell].paragraphs[0]
        elif t.type in ["th_close", "td_close"]:
            if t.type == "th_close":
                for run in paragraph.runs: run.bold = True
            paragraph = None
        elif t.type == "paragraph_open":
            paragraph = doc.add_paragraph()
            if lists or quotes: paragraph.paragraph_format.left_indent = Inches(.22 * (len(lists)+quotes))
            if pending_prefix: paragraph.add_run(pending_prefix); pending_prefix = None
        elif t.type == "paragraph_close": paragraph = None
        elif t.type == "inline":
            if heading is not None:
                paragraph = doc.add_heading("", heading)
                if pending_prefix: paragraph.add_run(pending_prefix); pending_prefix = None
            if paragraph is None: paragraph = doc.add_paragraph()
            inline_word(paragraph, t.children)
        elif t.type in ["fence", "code_block"]:
            p = doc.add_paragraph()
            if lists or quotes: p.paragraph_format.left_indent = Inches(.22 * (len(lists)+quotes))
            if pending_prefix: p.add_run(pending_prefix); pending_prefix = None
            p.paragraph_format.space_before = Pt(6); p.paragraph_format.space_after = Pt(6)
            run = p.add_run(t.content.rstrip("\n")); run.font.name = "Consolas"; run.font.size = Pt(9)
        elif t.type == "hr": doc.add_paragraph("─" * 40)


def html(text):
    # No external image loading; caller embeds only reviewed local media.
    md = MarkdownIt("commonmark", {"html": False}).enable("table").enable("strikethrough")
    md.add_render_rule("image", lambda self, tokens, idx, options, env: '<span class="image-reference">[Bild: '+escape(tokens[idx].content)+" – lokale Medienzuordnung erforderlich]</span>")
    return md.render(text)


def batch(files, combined=False, title="Markdown-Dokumente", template=None):
    from app import Invalid, clean_text
    from docx import Document
    if not isinstance(files, list) or not 1 <= len(files) <= 100:
        raise Invalid("1–100 Markdown-Dateien auswählen.")
    prepared = []
    for index, item in enumerate(files, 1):
        if not isinstance(item, dict): raise Invalid("Ungültiger Markdown-Dateieintrag.")
        name = PurePath(clean_text(item.get("name"), "Dateiname", 250).replace("\\", "/")).name
        if not name.lower().endswith((".md", ".markdown")):
            raise Invalid("Nur MD/Markdown-Dateien im Konverter verwenden.")
        text = clean_text(item.get("text"), "Markdown", 1_000_000)
        prepared.append((name, text))
    if sum(len(text) for _, text in prepared) > 5_000_000:
        raise Invalid("Maximal 5 Millionen Zeichen je Stapel.")

    def new_doc():
        if template:
            from layouts import word_document
            return word_document(template)
        return Document()

    if combined:
        doc = new_doc(); doc.add_heading(clean_text(title, "Dokumenttitel", 300), 0)
        for index, (name, text) in enumerate(prepared):
            if index: doc.add_page_break()
            doc.add_heading(PurePath(name).stem, 1); append_word(doc, text, 1)
        out = io.BytesIO(); doc.save(out)
        return out.getvalue(), "docx"
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for index, (name, text) in enumerate(prepared, 1):
            doc = new_doc(); append_word(doc, text)
            binary = io.BytesIO(); doc.save(binary)
            safe = re.sub(r"[^\w .-]", "_", PurePath(name).stem)[:120] or "Dokument"
            archive.writestr(f"{index:03d}-{safe}.docx", binary.getvalue())
    return out.getvalue(), "zip"
