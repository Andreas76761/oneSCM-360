"""Self-contained HTML and local, paginated PDF from the same approved output plan."""
import base64
import io
from html import escape
from pathlib import Path

import layouts
import markdown_tools

MIME = {"docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "html": "text/html; charset=utf-8", "pdf": "application/pdf", "zip": "application/zip"}


def html_export(plan, loader=None):
    from app import profile_caption, Invalid
    t = layouts.theme(plan.get("layout", {}).get("theme"))
    label = "PRÜFAUSGABE" if plan.get("draft", True) else "FREIGEGEBENE AUSGABE"
    parts = [f'<header><small>{label} · Version {escape(plan["metadata"]["version"])} · Revision {plan["revision"]}</small><h1>{escape(plan["title"])}</h1><p>{escape(profile_caption(plan["profile"]))}</p></header>']
    parts.extend('<p class="warning">Prüfpunkt: '+escape(w)+"</p>" for w in plan["warnings"])
    toc = []
    for c in plan["chapters"]:
        if not c["visible"]: continue
        anchor = "chapter-" + c["number"].replace(".", "-")
        toc.append(f'<li><a href="#{anchor}">{escape(c["number"]+" "+c["title"])}</a></li>')
        level = min(6, c["level"]+1)
        parts.append(f'<section id="{anchor}"><h{level}>{escape(c["number"]+" "+c["title"])}</h{level}>')
        for b in c["blocks"]:
            if plan["profile"]["division"] == "Beide" and b["division"] != "*":
                parts.append("<small>Gilt für: "+escape(b["division"])+"</small>")
            parts.append(markdown_tools.html(b["text"]) if b.get("text_format") == "markdown" else "<p>"+escape(b["text"]).replace("\n", "<br>")+"</p>")
        for figure in c.get("figures", []):
            parts.append("<h4>"+escape(figure["title"])+"</h4>")
            for frame in figure["frames"]:
                if not loader: raise Invalid("Bilddaten fehlen.")
                image = base64.b64encode(loader(frame["asset_id"], frame["revision"])).decode()
                caption = (f"Schritt {frame['step']}: " if figure["kind"] == "Klickstrecke" else "") + frame["caption"]
                parts.append(f'<figure><img src="data:image/png;base64,{image}" alt="{escape(caption,quote=True)}"><figcaption>{escape(caption)}</figcaption></figure>')
        if c["mandatory"] and not c["blocks"] and not c.get("figures"): parts.append("<p>[Inhalt ergänzen]</p>")
        parts.append("</section>")
    css = f"""body{{font:{t['size']}pt '{t['font']}',sans-serif;color:{t['text']};line-height:1.55;margin:3rem auto;padding:0 2rem;max-width:64rem}}h1,h2,h3,h4,h5,h6{{color:{t['primary']};break-after:avoid}}header{{border-bottom:4px solid {t['accent']};padding-bottom:1rem}}a{{color:{t['accent']}}}img{{max-width:100%;height:auto}}figure{{margin:1.5rem 0;break-inside:avoid}}figcaption,small{{color:{t['accent']}}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #b8c9cf;padding:.5rem;vertical-align:top}}pre{{white-space:pre-wrap;background:#f0f4f6;padding:1rem;overflow-wrap:anywhere}}p,td{{overflow-wrap:anywhere}}.warning{{border-left:4px solid #ad6b17;padding:.5rem 1rem}}@media print{{body{{max-width:none;margin:0}}nav{{display:none}}@page{{size:A4;margin:20mm}}}}"""
    return ('<!doctype html><html lang="'+escape(plan["profile"]["language"])+ '"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'"><title>'+escape(plan["title"])+"</title><style>"+css+"</style></head><body><nav aria-label=\"Inhaltsübersicht\"><ul>"+"".join(toc)+"</ul></nav>"+"".join(parts)+"</body></html>").encode()


def pdf_font(language):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    if language == "ko":
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        name = "HYSMyeongJo-Medium"
        if name not in pdfmetrics.getRegisteredFontNames(): pdfmetrics.registerFont(UnicodeCIDFont(name))
        pdfmetrics.registerFontFamily(name, normal=name, bold=name, italic=name, boldItalic=name)
        return name
    if "oneSCMUnicode" not in pdfmetrics.getRegisteredFontNames():
        import reportlab
        paths = [Path("C:/Windows/Fonts/arial.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"]
        path = next(p for p in paths if p.exists())
        pdfmetrics.registerFont(TTFont("oneSCMUnicode", str(path)))
        bold = path.with_name("arialbd.ttf" if path.name == "arial.ttf" else "DejaVuSans-Bold.ttf" if path.name == "DejaVuSans.ttf" else "VeraBd.ttf")
        pdfmetrics.registerFont(TTFont("oneSCMBold", str(bold if bold.exists() else path)))
        pdfmetrics.registerFontFamily("oneSCMUnicode", normal="oneSCMUnicode", bold="oneSCMBold", italic="oneSCMUnicode", boldItalic="oneSCMBold")
    return "oneSCMUnicode"


def pdf_inline(children):
    result = []
    for token in children or []:
        if token.type in ["text", "code_inline", "html_inline"]: result.append(escape(token.content))
        elif token.type == "image": result.append(escape("[Bild: "+token.content+" – Medienzuordnung erforderlich]"))
        elif token.type in ["softbreak", "hardbreak"]: result.append("<br/>")
        elif token.type in ["strong_open", "strong_close", "em_open", "em_close"]:
            tag = "b" if token.type.startswith("strong") else "i"; result.append("<"+("/" if token.type.endswith("close") else "")+tag+">")
    return "".join(result)


def pdf_export(plan, loader=None):
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from app import profile_caption, Invalid
    t = layouts.theme(plan.get("layout", {}).get("theme")); font = pdf_font(plan["profile"]["language"])
    normal = ParagraphStyle("body", fontName=font, fontSize=t["size"], leading=t["size"]*1.4, spaceAfter=8, textColor=colors.HexColor(t["text"]), splitLongWords=True)
    heading = ParagraphStyle("heading", parent=normal, fontSize=t["size"]+5, leading=t["size"]+10, textColor=colors.HexColor(t["primary"]), spaceBefore=14, keepWithNext=True)
    story = []; output = io.BytesIO(); width = A4[0]-100
    label = "PRÜFAUSGABE" if plan.get("draft", True) else "FREIGEGEBENE AUSGABE"
    story.extend([Paragraph(escape(plan["title"]), heading), Paragraph(escape(label+" · Version "+plan["metadata"]["version"]+" · R"+str(plan["revision"])), normal), Paragraph(escape(profile_caption(plan["profile"])), normal)])
    story.extend(Paragraph(escape("Prüfpunkt: "+w), normal) for w in plan["warnings"])
    for c in plan["chapters"]:
        if not c["visible"]: continue
        story.append(Paragraph(escape(c["number"]+" "+c["title"]), heading))
        for b in c["blocks"]:
            if b.get("text_format") == "markdown":
                in_table = False; table_rows = []; cells = []; depth = 0; heading_next = False; list_item = False
                for token in markdown_tools.tokens(b["text"]):
                    if token.type == "table_open": in_table=True; table_rows=[]
                    elif token.type == "table_close":
                        in_table=False
                        if table_rows:
                            count=max(len(r) for r in table_rows)
                            table_rows=[r+[Paragraph("",normal)]*(count-len(r)) for r in table_rows]
                            table=Table(table_rows,colWidths=[width/count]*count,repeatRows=1,hAlign="LEFT")
                            table.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.5,colors.HexColor(t["accent"])),("VALIGN",(0,0),(-1,-1),"TOP"),("BACKGROUND",(0,0),(-1,0),colors.HexColor("#edf3f5"))]))
                            story.extend([table, Spacer(1,10)])
                    elif token.type == "tr_open": cells=[]
                    elif token.type == "tr_close": table_rows.append(cells)
                    elif token.type.endswith("list_open"): depth+=1
                    elif token.type.endswith("list_close"): depth-=1
                    elif token.type == "list_item_open": list_item=True
                    elif token.type == "heading_open": heading_next=True
                    elif token.type == "inline":
                        content=pdf_inline(token.children)
                        if in_table: cells.append(Paragraph(content,normal))
                        else:
                            prefix=("• " if list_item else "")
                            style=heading if heading_next else ParagraphStyle("list",parent=normal,leftIndent=max(0,depth)*12)
                            story.append(Paragraph(prefix+content,style));heading_next=False;list_item=False
                    elif token.type in ["fence","code_block"]:
                        story.append(Paragraph(escape(token.content).replace("\n","<br/>"),normal))
            else:
                story.extend(Paragraph(escape(line) or "<br/>", normal) for line in b["text"].splitlines())
        for figure in c.get("figures", []):
            if figure["title"]: story.append(Paragraph(escape(figure["title"]),heading))
            for frame in figure["frames"]:
                if not loader: raise Invalid("Bilddaten fehlen.")
                w=min(width,480*frame["width"]/frame["height"]);h=w*frame["height"]/frame["width"]
                story.append(Image(io.BytesIO(loader(frame["asset_id"],frame["revision"])),width=w,height=h))
                caption=(f"Schritt {frame['step']}: " if figure["kind"]=="Klickstrecke" else "")+frame["caption"]
                story.append(Paragraph(escape(caption),normal))
        if c["mandatory"] and not c["blocks"] and not c.get("figures"): story.append(Paragraph("[Inhalt ergänzen]",normal))

    def footer(canvas, doc):
        canvas.saveState();canvas.setFont(font,8);canvas.setFillColor(colors.HexColor(t["accent"]))
        canvas.drawString(50,25,"oneSCM-360 · "+label);canvas.drawRightString(A4[0]-50,25,str(doc.page));canvas.restoreState()
    SimpleDocTemplate(output,pagesize=A4,leftMargin=50,rightMargin=50,topMargin=45,bottomMargin=45,title=plan["title"],author="oneSCM-360").build(story,onFirstPage=footer,onLaterPages=footer)
    return output.getvalue()
