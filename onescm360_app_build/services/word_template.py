"""Build a Word template (.dotx) or sample document (.docx) from a design template.

Pure zipfile + XML (no python-docx), so it runs with the two mandatory packages only.
Styles created: Normal, Title, Subtitle, Untertitel EN, Heading 1-3 (built-in names, so
Word's navigation and table of contents use them), Caption, Quellenzeile, Hinweis Info/Tipp/
Offen/Kritisch (left border + shading), Badge (character style) and the table style
"oneSCM Tabelle" (header row in the primary colour, optional zebra rows).
"""
from __future__ import annotations

import io
import zipfile
from xml.sax.saxutils import escape

from .design_service import fill

W_NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')
TWIPS_PER_CM = 567
PAGE_SIZES = {"A4": (11906, 16838), "Letter": (12240, 15840)}


def _style_id(name: str) -> str:
    return "".join(ch for ch in name.title() if ch.isalnum())[:40] or "Box"


def _box_ppr(t, box) -> str:
    """Paragraph border/shading for a layout box according to the box style (Word knows only paragraph borders)."""
    el = t["elements"]
    c, bg = box["color"].lstrip("#"), box["background"].lstrip("#")
    width = max(2, int(el["boxBorder"] * 6))  # px → eighths of a point
    style = el["boxStyle"]
    if style == "frame":
        side = max(2, width // 2)
        borders = "".join(f'<w:{s} w:val="single" w:sz="{side}" w:space="6" w:color="{c}"/>' for s in ("top", "left", "bottom", "right"))
        return f"<w:pBdr>{borders}</w:pBdr>"
    if style == "fill":
        return f'<w:shd w:val="clear" w:color="auto" w:fill="{c}"/>'
    if style == "card":
        return (f'<w:pBdr><w:top w:val="single" w:sz="{width}" w:space="6" w:color="{c}"/></w:pBdr>'
                f'<w:shd w:val="clear" w:color="auto" w:fill="{bg}"/>')
    if style == "minimal":
        line = _hex(t, "line")
        return (f'<w:pBdr><w:top w:val="single" w:sz="4" w:space="6" w:color="{line}"/>'
                f'<w:bottom w:val="single" w:sz="4" w:space="6" w:color="{line}"/></w:pBdr>')
    return (f'<w:pBdr><w:left w:val="single" w:sz="{width}" w:space="8" w:color="{c}"/></w:pBdr>'
            f'<w:shd w:val="clear" w:color="auto" w:fill="{bg}"/>')


def _hex(t, key):
    return t["colors"][key].lstrip("#")


def _run_props(t, element, color_key=None):
    e = t["typography"][element]
    font = t["fonts"][e["font"]]
    props = [f'<w:rFonts w:ascii="{font}" w:hAnsi="{font}" w:cs="{font}"/>']
    if e["weight"] >= 600:
        props.append("<w:b/><w:bCs/>")
    if e["italic"]:
        props.append("<w:i/><w:iCs/>")
    if e["uppercase"]:
        props.append("<w:caps/>")
    props.append(f'<w:color w:val="{_hex(t, color_key or e["color"])}"/>')
    half_points = int(round(e["size"] * 2))
    props.append(f'<w:sz w:val="{half_points}"/><w:szCs w:val="{half_points}"/>')
    return "<w:rPr>" + "".join(props) + "</w:rPr>"


def _spacing(e):
    return (f'<w:spacing w:before="{int(e["before"] * 20)}" w:after="{int(e["after"] * 20)}" '
            f'w:line="{int(round(e["lineHeight"] * 240))}" w:lineRule="auto"/>')


def _paragraph_style(t, style_id, name, element, *, based="Normal", outline=None, extra_ppr="", default=False, color_key=None):
    e = t["typography"][element]
    ppr = _spacing(e) + extra_ppr
    if outline is not None:
        ppr = "<w:keepNext/><w:keepLines/>" + ppr + f'<w:outlineLvl w:val="{outline}"/>'
    based_xml = f'<w:basedOn w:val="{based}"/>' if based else ""
    default_xml = ' w:default="1"' if default else ""
    return (f'<w:style w:type="paragraph"{default_xml} w:styleId="{style_id}">'
            f'<w:name w:val="{name}"/>{based_xml}<w:next w:val="Normal"/><w:qFormat/>'
            f"<w:pPr>{ppr}</w:pPr>{_run_props(t, element, color_key)}</w:style>")


def styles_xml(t: dict) -> str:
    body_font = t["fonts"][t["typography"]["body"]["font"]]
    el = t["elements"]
    parts = [f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {W_NS}>',
             "<w:docDefaults><w:rPrDefault><w:rPr>"
             f'<w:rFonts w:ascii="{body_font}" w:hAnsi="{body_font}" w:cs="{body_font}" w:eastAsia="{body_font}"/>'
             f'<w:sz w:val="{int(t["typography"]["body"]["size"] * 2)}"/><w:lang w:val="de-DE"/>'
             "</w:rPr></w:rPrDefault><w:pPrDefault><w:pPr>" + _spacing(t["typography"]["body"]) + "</w:pPr></w:pPrDefault></w:docDefaults>",
             _paragraph_style(t, "Normal", "Normal", "body", based=None, default=True),
             _paragraph_style(t, "Title", "Title", "title"),
             _paragraph_style(t, "Subtitle", "Subtitle", "subtitle"),
             _paragraph_style(t, "UntertitelEN", "Untertitel EN", "subtitleEn"),
             _paragraph_style(t, "Heading1", "heading 1", "h1", outline=0,
                              extra_ppr=(f'<w:pBdr><w:bottom w:val="single" w:sz="12" w:space="4" w:color="{_hex(t, "petrol")}"/></w:pBdr>'
                                         if el["h1Rule"] else "")),
             _paragraph_style(t, "Heading2", "heading 2", "h2", outline=1),
             _paragraph_style(t, "Heading3", "heading 3", "h3", outline=2),
             _paragraph_style(t, "Caption", "caption", "caption"),
             _paragraph_style(t, "Quellenzeile", "Quellenzeile", "source")]
    for box in t["boxes"]:
        style = _paragraph_style(t, _style_id(box["wordStyle"]), box["wordStyle"], "box",
                                 extra_ppr=_box_ppr(t, box) + '<w:ind w:left="170" w:right="113"/>')
        if el["boxStyle"] == "fill":  # white text on the coloured surface
            style = style.replace(f'<w:color w:val="{_hex(t, t["typography"]["box"]["color"])}"/>', '<w:color w:val="FFFFFF"/>')
        parts.append(style)
    parts.append(_paragraph_style(t, "PlatzhalterBild", "Platzhalter Bild", "caption",
                                  extra_ppr=(f'<w:pBdr>' + "".join(f'<w:{s} w:val="dashed" w:sz="12" w:space="12" w:color="{_hex(t, "placeholder")}"/>'
                                                                   for s in ("top", "left", "bottom", "right")) + "</w:pBdr>"
                                             f'<w:shd w:val="clear" w:color="auto" w:fill="{_hex(t, "soft")}"/><w:jc w:val="center"/>'),
                                  color_key="muted").replace("<w:i/><w:iCs/>", ""))
    badge = t["typography"]["badge"]
    parts.append('<w:style w:type="character" w:styleId="Badge"><w:name w:val="Badge"/><w:qFormat/>'
                 f'<w:rPr><w:b/><w:caps/><w:color w:val="{_hex(t, "warn")}"/><w:sz w:val="{int(badge["size"] * 2)}"/>'
                 f'<w:shd w:val="clear" w:color="auto" w:fill="{_hex(t, "warnBg")}"/></w:rPr></w:style>')
    head_style = el.get("tableHeadStyle", "dark")
    if head_style == "dark":
        head_rpr, head_tcpr = _run_props(t, "tableHead"), f'<w:shd w:val="clear" w:color="auto" w:fill="{_hex(t, el["tableHeadBg"])}"/>'
    else:
        head_rpr = _run_props(t, "tableHead", "navy")
        rule = _hex(t, "petrol" if head_style == "light" else "navy")
        head_tcpr = (f'<w:tcBorders><w:bottom w:val="single" w:sz="12" w:color="{rule}"/></w:tcBorders>'
                     + (f'<w:shd w:val="clear" w:color="auto" w:fill="{_hex(t, "soft")}"/>' if head_style == "light" else ""))
    pad_v, pad_h = int(el["cellPaddingV"] * 20), int(el["cellPaddingH"] * 20)
    line = _hex(t, "line")
    zebra = (f'<w:tblStylePr w:type="band2Horz"><w:tcPr><w:shd w:val="clear" w:color="auto" w:fill="{_hex(t, "soft")}"/></w:tcPr></w:tblStylePr>'
             if el["tableZebra"] else "")
    parts.append(
        '<w:style w:type="table" w:styleId="oneSCMTabelle"><w:name w:val="oneSCM Tabelle"/><w:basedOn w:val="TableNormal"/><w:qFormat/>'
        f"<w:pPr><w:spacing w:before=\"0\" w:after=\"0\"/></w:pPr>{_run_props(t, 'tableBody')}"
        f'<w:tblPr><w:tblStyleRowBandSize w:val="1"/><w:tblBorders><w:bottom w:val="single" w:sz="4" w:color="{line}"/>'
        f'<w:insideH w:val="single" w:sz="4" w:color="{line}"/></w:tblBorders>'
        f'<w:tblCellMar><w:top w:w="{pad_v}" w:type="dxa"/><w:left w:w="{pad_h}" w:type="dxa"/>'
        f'<w:bottom w:w="{pad_v}" w:type="dxa"/><w:right w:w="{pad_h}" w:type="dxa"/></w:tblCellMar></w:tblPr>'
        f'<w:tblStylePr w:type="firstRow">{head_rpr}'
        f'<w:tcPr>{head_tcpr}</w:tcPr></w:tblStylePr>{zebra}</w:style>')
    parts.append('<w:style w:type="table" w:default="1" w:styleId="TableNormal"><w:name w:val="Normal Table"/>'
                 '<w:tblPr><w:tblInd w:w="0" w:type="dxa"/><w:tblCellMar><w:top w:w="0" w:type="dxa"/><w:left w:w="108" w:type="dxa"/>'
                 '<w:bottom w:w="0" w:type="dxa"/><w:right w:w="108" w:type="dxa"/></w:tblCellMar></w:tblPr></w:style>')
    parts.append("</w:styles>")
    return "".join(parts)


def _p(style, text, runs=None):
    content = runs if runs is not None else f'<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r>'
    return f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr>{content}</w:p>'


def _hf(t, kind, text, values):
    """Header/footer paragraph; {page}/{pages} become Word fields."""
    runs = []
    rpr = (f'<w:rPr><w:color w:val="{_hex(t, "muted")}"/><w:sz w:val="{int(t["typography"]["source"]["size"] * 2)}"/></w:rPr>')
    text = fill(text, {k: v for k, v in values.items() if k not in ("page", "pages")})
    for token in text.replace("{page}", "\x00PAGE\x00").replace("{pages}", "\x00NUMPAGES\x00").split("\x00"):
        if token in ("PAGE", "NUMPAGES"):
            runs.append(f'<w:fldSimple w:instr=" {token} "><w:r>{rpr}<w:t>1</w:t></w:r></w:fldSimple>')
        elif token:
            runs.append(f'<w:r>{rpr}<w:t xml:space="preserve">{escape(token)}</w:t></w:r>')
    tag = "hdr" if kind == "header" else "ftr"
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:{tag} {W_NS}>'
            f'<w:p><w:pPr><w:spacing w:before="0" w:after="0"/></w:pPr>{"".join(runs)}</w:p></w:{tag}>')


def _box_paragraph(t, box) -> str:
    """Sample paragraph of a layout box: Word symbol and bold title in the box colour, then the text."""
    color = "FFFFFF" if t["elements"]["boxStyle"] == "fill" else box["color"].lstrip("#")
    head = f'{box["symbol"]} {box["title"]} '.lstrip()
    return _p(_style_id(box["wordStyle"]), "",
              f'<w:r><w:rPr><w:b/><w:color w:val="{color}"/></w:rPr><w:t xml:space="preserve">{escape(head)}</w:t></w:r>'
              f'<w:r><w:t xml:space="preserve">{escape(box["text"])}</w:t></w:r>')


def document_xml(t: dict, values: dict) -> str:
    rows = [("Bereich", "Zweck", "Hauptrolle", "Sparte"),
            ("Contract Calculation", "Produkte anlegen, Preise und Gruppen zuordnen.", "MPC", "beide"),
            ("Contract Management", "Aktive Verträge einsehen und Status ändern.", "Power User", "PC"),
            ("Revenue Management", "Rechnungen und Gutschriften erstellen.", "Market Operation", "Van")]
    table = ['<w:tbl><w:tblPr><w:tblStyle w:val="oneSCMTabelle"/><w:tblW w:w="5000" w:type="pct"/>'
             '<w:tblLook w:val="04A0" w:firstRow="1" w:lastRow="0" w:firstColumn="0" w:lastColumn="0" w:noHBand="0" w:noVBand="1"/></w:tblPr>'
             '<w:tblGrid>' + '<w:gridCol w:w="2000"/>' * 4 + "</w:tblGrid>"]
    for i, row in enumerate(rows):
        header = '<w:trPr><w:tblHeader/></w:trPr>' if i == 0 else ""
        table.append(f"<w:tr>{header}" + "".join(f'<w:tc><w:tcPr><w:tcW w:w="1250" w:type="pct"/></w:tcPr><w:p><w:r><w:t>{escape(c)}</w:t></w:r></w:p></w:tc>'
                                                  for c in row) + "</w:tr>")
    table.append("</w:tbl>")
    width, height = PAGE_SIZES[t["page"]["format"]]
    orient = ""
    if t["page"]["orientation"] == "landscape":
        width, height = height, width
        orient = ' w:orient="landscape"'
    m = {k: int(t["page"][k] * TWIPS_PER_CM) for k in ("marginTop", "marginRight", "marginBottom", "marginLeft")}
    badge = '<w:r><w:rPr><w:rStyle w:val="Badge"/></w:rPr><w:t>Offen – Validierung erforderlich</w:t></w:r>'
    body = "".join([
        _p("Title", t["documentTitle"]), _p("Subtitle", f"Kapitel {values['chapter']} – {values['chapterTitle']}"),
        _p("UntertitelEN", "English Chapter Title"),

        _p("Heading1", "1 Überschrift 1"), _p("Heading2", "1.1 Überschrift 2"), _p("Heading3", "Überschrift 3"),
        _p("Normal", "Fließtext in der Formatvorlage „Standard“. Status-Kennzeichnung als Zeichenformat „Badge“: ", None)[:-6]
        + badge + "</w:p>",
        "".join(table), _p("Quellenzeile", "Quellen: ONESCM-77, -78, -593"),
        "".join(_box_paragraph(t, box) for box in t["boxes"]),
        _p("PlatzhalterBild", "", '<w:r><w:rPr><w:b/></w:rPr><w:t>SCREENSHOT</w:t></w:r><w:r><w:br/>'
                                  '<w:t>[Maske / Bereich] – Bild hier einfügen</w:t></w:r>'),
        _p("Caption", "Abbildung 1.1 – [Titel] · Rolle: [MPC / MO / Dealer] · Sparte: [PC / Van]"),
    ])
    sect = (f'<w:sectPr><w:headerReference w:type="default" r:id="rIdHeader1"/><w:footerReference w:type="default" r:id="rIdFooter1"/>'
            f'<w:pgSz w:w="{width}" w:h="{height}"{orient}/><w:pgMar w:top="{m["marginTop"]}" w:right="{m["marginRight"]}" '
            f'w:bottom="{m["marginBottom"]}" w:left="{m["marginLeft"]}" w:header="567" w:footer="567" w:gutter="0"/>'
            f'<w:cols w:num="{t["page"]["columns"]}" w:space="567"/></w:sectPr>')
    return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W_NS}><w:body>{body}{sect}</w:body></w:document>'


def build(t: dict, kind: str = "dotx") -> bytes:
    if kind not in ("dotx", "docx"):
        raise ValueError("kind must be dotx or docx")
    values = {"chapter": "XX", "chapterTitle": "Kapiteltitel", "version": "V.X", "date": "TT.MM.JJJJ", "stage": "Draft", "release": "R.X"}
    main_type = ("application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml" if kind == "dotx"
                 else "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml")
    content_types = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                     '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                     '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                     '<Default Extension="xml" ContentType="application/xml"/>'
                     f'<Override PartName="/word/document.xml" ContentType="{main_type}"/>'
                     '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
                     '<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
                     '<Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>'
                     '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
                     '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
                     "</Types>")
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
            "</Relationships>")
    doc_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                '<Relationship Id="rIdSettings" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>'
                '<Relationship Id="rIdHeader1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>'
                '<Relationship Id="rIdFooter1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>'
                "</Relationships>")
    settings = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:settings {W_NS}>'
                '<w:defaultTabStop w:val="708"/><w:characterSpacingControl w:val="doNotCompress"/></w:settings>')
    core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>' + escape(t["name"]) + "</dc:title>"
            "<dc:creator>oneSCM360 Knowledge Studio</dc:creator></cp:coreProperties>")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/_rels/document.xml.rels", doc_rels)
        z.writestr("word/document.xml", document_xml(t, values))
        z.writestr("word/styles.xml", styles_xml(t))
        z.writestr("word/settings.xml", settings)
        z.writestr("word/header1.xml", _hf(t, "header", t["header"], values))
        z.writestr("word/footer1.xml", _hf(t, "footer", t["footer"], values))
        z.writestr("docProps/core.xml", core)
    return buffer.getvalue()
