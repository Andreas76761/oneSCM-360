"""Self-contained HTML and local, paginated PDF from the same approved output plan."""
import base64
import io
import re
from html import escape, unescape
from html.parser import HTMLParser
from pathlib import Path

import layouts
import markdown_tools

MIME = {"docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "html": "text/html; charset=utf-8", "pdf": "application/pdf", "zip": "application/zip"}


def callout_kind(text):
    """Only explicit, reader-visible labels trigger a callout; never internal notes."""
    match = re.match(r"^\s*(?:>\s*)?(?:\*\*)?(Hinweis|Notice|Note|Tipp|Tip|Ausnahme|Exception|Achtung|Attention|Warning|Warnung|Remarque|Conseil|Nota|Suggerimento|Attenzione|Eccezione|Poznámka|Upozornenie|Výnimka|참고|주의|팁|예외)\s*:", text, re.I)
    return ({"hinweis": "notice", "notice": "notice", "note": "notice", "tipp": "tip", "tip": "tip",
             "ausnahme": "exception", "exception": "exception", "achtung":"attention", "attention":"attention", "warning":"attention", "warnung":"attention", "remarque":"notice", "conseil":"tip", "nota":"notice", "suggerimento":"tip", "attenzione":"attention", "eccezione":"exception", "poznámka":"notice", "upozornenie":"attention", "výnimka":"exception", "참고":"notice", "주의":"attention", "팁":"tip", "예외":"exception"}.get(match[1].lower()) if match else None)


def callout_icon(kind, theme):
    if not kind or not theme["icons"]: return ""
    icons = {"symbols": {"notice":"ℹ", "tip":"✓", "exception":"!", "attention":"!"},
             "letters": {"notice":"H", "tip":"T", "exception":"A", "attention":"!"},
             "minimal": {"notice":"•", "tip":"•", "exception":"•", "attention":"•"},
             "outline":{"notice":"ⓘ","tip":"✓","exception":"!","attention":"!"}}
    return icons[theme.get("icon_style","symbols")][kind]


def icon_svg(kind):
    paths={"notice":'<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7v1"/>',
           "tip":'<path d="M9 18h6M10 21h4M8 14a6 6 0 1 1 8 0l-1 3H9z"/>',
           "attention":'<path d="M12 3 2 21h20zM12 9v5M12 17v1"/>',
           "exception":'<path d="M8 3h8l5 5v8l-5 5H8l-5-5V8zM12 7v6M12 16v1"/>'}
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'+paths[kind]+'</svg>'


def icon_png(kind,color):
    from PIL import Image,ImageDraw
    image=Image.new("RGBA",(96,96),(0,0,0,0));d=ImageDraw.Draw(image);w=6
    if kind=="notice":
        d.ellipse((10,10,86,86),outline=color,width=w);d.line((48,43,48,69),fill=color,width=w);d.ellipse((44,26,52,34),fill=color)
    elif kind=="tip":
        d.ellipse((21,8,75,62),outline=color,width=w);d.line([(32,57),(36,73),(60,73),(64,57)],fill=color,width=w);d.line((37,84,59,84),fill=color,width=w)
    else:
        points=[(48,8),(7,85),(89,85),(48,8)] if kind=="attention" else [(30,8),(66,8),(88,30),(88,66),(66,88),(30,88),(8,66),(8,30),(30,8)]
        d.line(points,fill=color,width=w,joint="curve");d.line((48,31,48,55),fill=color,width=w);d.ellipse((44,65,52,73),fill=color)
    output=io.BytesIO();image.save(output,format="PNG");return output.getvalue()


def pdf_icon(kind,theme):
    if not kind or not theme["icons"]:return ""
    if theme["icon_style"]!="outline":return callout_icon(kind,theme)+" "
    data=base64.b64encode(icon_png(kind,theme[kind+"_border_color"])).decode()
    size=theme["size"]
    return f'<img src="data:image/png;base64,{data}" width="{size}" height="{size}" valign="middle"/> '


def keyword_segments(text, theme):
    words = theme.get("keywords", [])
    if not words: return [(text, False)]
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True)) + r")(?!\w)", re.I)
    result = []; start = 0
    for match in pattern.finditer(text):
        if match.start() > start: result.append((text[start:match.start()], False))
        result.append((match[0], True)); start = match.end()
    if start < len(text): result.append((text[start:], False))
    return result


def highlighted(text, theme, pdf=False):
    tag = 'font backColor="' + theme["highlight"] + '"' if pdf else "mark"
    close = "font" if pdf else "mark"
    return "".join(("<"+tag+">"+escape(s)+"</"+close+">") if marked else escape(s) for s, marked in keyword_segments(text, theme))


def styled_html(text, theme, markdown=False):
    raw = markdown_tools.html(text) if markdown else "".join("<p>"+escape(line)+"</p>" for line in text.splitlines() if line.strip())
    class Highlight(HTMLParser):
        def __init__(self): super().__init__(convert_charrefs=True); self.parts=[]; self.code=0
        def handle_starttag(self, tag, attrs):
            self.parts.append(self.get_starttag_text())
            if tag in {"code", "pre"}: self.code += 1
        def handle_startendtag(self, tag, attrs): self.parts.append(self.get_starttag_text())
        def handle_endtag(self, tag):
            self.parts.append("</"+tag+">")
            if tag in {"code", "pre"}: self.code = max(0, self.code-1)
        def handle_data(self, data): self.parts.append(escape(data) if self.code else highlighted(data, theme))
    parser = Highlight(); parser.feed(raw); parser.close(); content = "".join(parser.parts)
    def callout(match):
        kind=callout_kind(unescape(re.sub(r"<[^>]+>","",match[1])))
        if not kind:return match[0]
        icon=''
        if theme["icons"]:
            glyph=icon_svg(kind) if theme["icon_style"]=="outline" else callout_icon(kind,theme)
            icon='<span class="callout-icon" aria-hidden="true">'+glyph+'</span>'
        return '<aside class="callout '+kind+'">'+icon+match[0]+'</aside>'
    content=re.sub(r"<p>(.*?)</p>",callout,content,flags=re.S)

    return content


def slide_markdown(text):
    """Readable slide text and safe links; no remote images or raw HTML execution."""
    class Plain(HTMLParser):
        def __init__(self): super().__init__(); self.parts=[]; self.href=None; self.label=[]; self.links={}
        def handle_starttag(self, tag, attrs):
            if tag in {"p","h1","h2","h3","h4","h5","h6","tr","pre","blockquote"}: self.parts.append("\n")
            elif tag == "li": self.parts.append("\n• ")
            elif tag == "br": self.parts.append("\n")
            if tag == "a": self.href=dict(attrs).get("href",""); self.label=[]
        def handle_endtag(self, tag):
            if tag in {"p","li","h1","h2","h3","h4","h5","h6","tr","pre","blockquote"}: self.parts.append("\n")
            elif tag in {"td","th"}: self.parts.append(" | ")
            elif tag == "a":
                if self.href and re.match(r"^(https?://|mailto:)", self.href,re.I):
                    self.links.setdefault("".join(self.label),set()).add(self.href)
                self.href=None
        def handle_data(self, value):
            self.parts.append(value)
            if self.href is not None: self.label.append(value)
    parser=Plain();parser.feed(markdown_tools.html(text));parser.close()
    content=re.sub(r"\n{3,}","\n\n","".join(parser.parts)).strip()
    return content,{label:next(iter(hrefs)) for label,hrefs in parser.links.items() if label and len(hrefs)==1}


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
            parts.append(styled_html(b["text"], t, b.get("text_format") == "markdown"))
        for figure in c.get("figures", []):
            parts.append("<h4>"+escape(figure["title"])+"</h4>")
            for frame in figure["frames"]:
                if not loader: raise Invalid("Bilddaten fehlen.")
                image = base64.b64encode(loader(frame["asset_id"], frame["revision"])).decode()
                caption = (f"Schritt {frame['step']}: " if figure["kind"] == "Klickstrecke" else "") + frame["caption"]
                caption_html = "<figcaption>"+escape(caption)+"</figcaption>" if t["captions"] else ""
                parts.append(f'<figure><img src="data:image/png;base64,{image}" alt="{escape(caption,quote=True)}">{caption_html}</figure>')
        if c["mandatory"] and not c["blocks"] and not c.get("figures"): parts.append("<p>[Inhalt ergänzen]</p>")
        parts.append("</section>")
    css = f"""body{{font:{t['size']}pt '{t['font']}',sans-serif;color:{t['text']};line-height:1.55;margin:3rem auto;padding:0 2rem;max-width:64rem}}h1,h2,h3,h4,h5,h6{{color:{t['primary']};break-after:avoid}}header{{border-bottom:4px solid {t['accent']};padding-bottom:1rem}}a{{color:{t['accent']}}}img{{max-width:100%;height:auto}}figure{{margin:1.5rem 0;break-inside:avoid}}figcaption,small{{color:{t['accent']}}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #b8c9cf;padding:.5rem;vertical-align:top}}pre{{white-space:pre-wrap;background:#f0f4f6;padding:1rem;overflow-wrap:anywhere}}p,td{{overflow-wrap:anywhere}}.warning{{border-left:4px solid #ad6b17;padding:.5rem 1rem}}@media print{{body{{max-width:none;margin:0}}nav{{display:none}}@page{{size:A4;margin:20mm}}}}"""
    css += f"h2{{color:{t['chapter']}}}h3,h4,h5,h6{{color:{t['subchapter']}}}a{{color:{t['link']}}}figure img{{max-width:{t['image_width']}%}}mark{{background:{t['highlight']};color:inherit}}.callout{{padding:.75rem 1rem;border-left:4px solid {t['accent']};margin:1rem 0;break-inside:avoid}}.callout p:first-of-type{{margin-top:0}}.callout p:last-child{{margin-bottom:0}}.callout-icon{{float:left;font-weight:bold;margin-right:.6rem}}.notice{{background:{t['notice']}}}.tip{{background:{t['tip']}}}.exception{{background:{t['exception']}}}"
    css += f"body{{line-height:{t['line_height']}}}h2{{font-family:'{t['chapter_font']}';font-size:{t['chapter_size']}pt;line-height:{t['chapter_line']}}}h3,h4,h5,h6{{font-family:'{t['subchapter_font']}';font-size:{t['subchapter_size']}pt;line-height:{t['subchapter_line']}}}"
    for kind in ["notice","exception","tip","attention"]:
        border=('1px solid '+t[kind+'_border_color']) if t[kind+'_border'] else 'none'
        css += f".callout.{kind}{{background:{t[kind]};border:{border};color:{t['text']}}}.callout.{kind} .callout-icon{{color:{t[kind+'_border_color']}}}"
    if t["page_numbers"]: css += '@media print{@page{@bottom-right{content:counter(page)}}}'
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


def pdf_design_font(family,language):
    if language=="ko":return pdf_font(language)
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    group="mono" if any(w in family.casefold() for w in ["courier","mono","consolas"]) else "serif" if any(w in family.casefold() for w in ["times","georgia","serif"]) else "sans"
    files={"mono":("cour.ttf","DejaVuSansMono.ttf"),"serif":("times.ttf","DejaVuSerif.ttf"),"sans":("arial.ttf","DejaVuSans.ttf")}
    paths=[Path("C:/Windows/Fonts")/files[group][0],Path("/usr/share/fonts/truetype/dejavu")/files[group][1]]
    path=next((p for p in paths if p.exists()),None)
    if not path:return pdf_font(language)
    name="oneSCM-"+group
    if name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(name,str(path)))
        pdfmetrics.registerFontFamily(name,normal=name,bold=name,italic=name,boldItalic=name)
    return name


def pdf_inline(children, theme=None):
    theme = theme or layouts.theme()
    result = []
    links = []
    for token in children or []:
        if token.type in ["text", "html_inline"]: result.append(highlighted(token.content, theme, pdf=True))
        elif token.type == "code_inline": result.append(escape(token.content))
        elif token.type == "image": result.append(escape("[Bild: "+token.content+" – Medienzuordnung erforderlich]"))
        elif token.type in ["softbreak", "hardbreak"]: result.append("<br/>")
        elif token.type in ["strong_open", "strong_close", "em_open", "em_close"]:
            tag = "b" if token.type.startswith("strong") else "i"; result.append("<"+("/" if token.type.endswith("close") else "")+tag+">")
        elif token.type == "link_open":
            href = token.attrGet("href") or ""
            safe = bool(re.match(r"^(https?://|mailto:)", href, re.I)); links.append(safe)
            if safe: result.append('<link href="'+escape(href, quote=True)+'" color="'+theme["link"]+'">')
        elif token.type == "link_close":
            if links and links.pop(): result.append("</link>")
    return "".join(result)


def pdf_export(plan, loader=None):
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from app import profile_caption, Invalid
    t = layouts.theme(plan.get("layout", {}).get("theme")); font = pdf_design_font(t["font"],plan["profile"]["language"])
    normal = ParagraphStyle("body", fontName=font, fontSize=t["size"], leading=t["size"]*t["line_height"], spaceAfter=8, textColor=colors.HexColor(t["text"]), splitLongWords=True)
    heading = ParagraphStyle("heading", parent=normal, fontName=pdf_design_font(t["chapter_font"],plan["profile"]["language"]), fontSize=t["chapter_size"], leading=t["chapter_size"]*t["chapter_line"], textColor=colors.HexColor(t["chapter"]), spaceBefore=14, keepWithNext=True)
    subheading = ParagraphStyle("subheading", parent=heading, fontName=pdf_design_font(t["subchapter_font"],plan["profile"]["language"]), fontSize=t["subchapter_size"], leading=t["subchapter_size"]*t["subchapter_line"], textColor=colors.HexColor(t["subchapter"]))
    caption_style = ParagraphStyle("caption", parent=normal, fontSize=max(8,t["size"]-1), textColor=colors.HexColor(t["accent"]))
    callouts = {kind: ParagraphStyle(kind,parent=normal,backColor=colors.HexColor(t[kind]),borderColor=colors.HexColor(t[kind+"_border_color"]),borderWidth=1 if t[kind+"_border"] else 0,borderPadding=7,leftIndent=8,rightIndent=8,spaceBefore=7,spaceAfter=12) for kind in ["notice","tip","exception","attention"]}
    story = []; output = io.BytesIO(); width = A4[0]-100
    label = "PRÜFAUSGABE" if plan.get("draft", True) else "FREIGEGEBENE AUSGABE"
    story.extend([Paragraph(escape(plan["title"]), heading), Paragraph(escape(label+" · Version "+plan["metadata"]["version"]+" · R"+str(plan["revision"])), normal), Paragraph(escape(profile_caption(plan["profile"])), normal)])
    story.extend(Paragraph(escape("Prüfpunkt: "+w), normal) for w in plan["warnings"])
    for c in plan["chapters"]:
        if not c["visible"]: continue
        story.append(Paragraph(escape(c["number"]+" "+c["title"]), heading if c["level"] == 1 else subheading))
        for b in c["blocks"]:
            if plan["profile"]["division"] == "Beide" and b["division"] != "*":
                story.append(Paragraph(escape("Gilt für: "+b["division"]),caption_style))
            kind = callout_kind(b["text"]); body_style = callouts.get(kind,normal)
            icon = callout_icon(kind,t)
            if icon: icon += " "
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
                        content=pdf_inline(token.children,t)
                        if in_table: cells.append(Paragraph(content,normal))
                        else:
                            inline_kind=None if heading_next else callout_kind(token.content)
                            body_style=callouts.get(inline_kind,normal)
                            glyph=pdf_icon(inline_kind,t)
                            prefix=glyph+("• " if list_item else "")
                            style=subheading if heading_next else ParagraphStyle("list",parent=body_style,leftIndent=body_style.leftIndent+max(0,depth)*12)
                            story.append(Paragraph(prefix+content,style));heading_next=False;list_item=False
                    elif token.type in ["fence","code_block"]:
                        story.append(Paragraph(escape(token.content).replace("\n","<br/>"),normal))
            else:
                for line in b["text"].splitlines():
                    line_kind = callout_kind(line)
                    line_style = callouts.get(line_kind,normal)
                    prefix=pdf_icon(line_kind,t)
                    story.append(Paragraph(prefix+highlighted(line,t,pdf=True) or "<br/>",line_style));icon=""
        for figure in c.get("figures", []):
            if figure["title"]: story.append(Paragraph(escape(figure["title"]),heading))
            for frame in figure["frames"]:
                if not loader: raise Invalid("Bilddaten fehlen.")
                w=min(width*t["image_width"]/100,480*frame["width"]/frame["height"]);h=w*frame["height"]/frame["width"]
                story.append(Image(io.BytesIO(loader(frame["asset_id"],frame["revision"])),width=w,height=h))
                caption=(f"Schritt {frame['step']}: " if figure["kind"]=="Klickstrecke" else "")+frame["caption"]
                if t["captions"]: story.append(Paragraph(escape(caption),caption_style))
        if c["mandatory"] and not c["blocks"] and not c.get("figures"): story.append(Paragraph("[Inhalt ergänzen]",normal))

    def footer(canvas, doc):
        canvas.saveState();canvas.setFont(font,8);canvas.setFillColor(colors.HexColor(t["accent"]))
        canvas.drawString(50,25,"oneSCM-360 · "+label)
        if t["page_numbers"]: canvas.drawRightString(A4[0]-50,25,str(doc.page))
        canvas.restoreState()
    SimpleDocTemplate(output,pagesize=A4,leftMargin=50,rightMargin=50,topMargin=45,bottomMargin=45,title=plan["title"],author="oneSCM-360").build(story,onFirstPage=footer,onLaterPages=footer)
    return output.getvalue()
