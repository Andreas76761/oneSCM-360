"""Browser acceptance: internal FAQ, publication controls, templates, MD and agents."""
import io
import os
from pathlib import Path
import sys
import tempfile
import threading

from docx import Document
from pypdf import PdfReader
from playwright.sync_api import sync_playwright, expect

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from test_publishing import office_parts
from test_media import sample_image


def main():
    with tempfile.TemporaryDirectory() as directory:
        store=app.Store(Path(directory)/"browser.sqlite3")
        outline=app.new_outline("Publishing acceptance")
        outline["chapters"]=[app.chapter("Contract")]
        outline["chapters"][0]["config"]={"status":"Freigegeben"}
        outline["chapters"][0]["blocks"]=[dict(app.block(),text="Open contract. SCM-42",status="Freigegeben")]
        store.save(outline)
        server=app.make_server(store,0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True,executable_path=os.environ.get("ONESCM_BROWSER_PATH"))
                page=browser.new_page(viewport={"width":1600,"height":1100})
                errors=[];page.on("pageerror",lambda error:errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{server.server_port}")
                expect(page.locator("#app-version")).to_contain_text("0.4.0")
                page.get_by_role("button",name="Publishing acceptance",exact=True).click()
                # Separate internal topic hierarchy and FAQ; no outline save needed.
                page.locator("#internal-button").click()
                expect(page.locator("#internal-tree")).to_contain_text("Testing")
                page.locator("#internal-categories-button").click()
                page.locator("#internal-category-name").fill("Regression")
                page.locator("#internal-category-parent").select_option("internal-testing")
                page.locator("#internal-category-add").click()
                page.locator("#internal-category-save").click()
                expect(page.locator("#internal-tree")).to_contain_text("Regression")
                page.locator("#internal-new").click()
                page.locator("#internal-title").fill("Internal regression")
                page.locator("#internal-body").fill("PRIVATE_TESTING_INFO")
                page.locator("#internal-question").fill("How is testing done?")
                page.locator("#internal-answer").fill("PRIVATE_FAQ_ANSWER")
                page.locator("#internal-entry-categories").select_option(["internal-testing","internal-it"])
                page.locator("#internal-entry-domains").select_option("d3")
                page.locator("#internal-entry-roles").select_option("HQ")
                page.locator("#internal-entry-markets").fill("DE")
                page.locator("#internal-entry-labels").fill("Regression, Release")
                page.locator("#internal-entry-status").select_option("Freigegeben")
                page.locator("#internal-enabled").check()
                page.get_by_role("button",name="Interne Revision speichern",exact=True).click()
                expect(page.locator("#internal-list")).to_contain_text("Internal regression")
                page.locator("#internal-search").fill("Regression")
                expect(page.locator("#internal-list .internal-card")).to_have_count(1)
                page.locator("#internal-dialog details").filter(has=page.locator("#internal-chat-query")).locator("summary").click()
                page.locator("#internal-chat-query").fill("testing")
                page.locator("#internal-chat-role").select_option("HQ")
                page.locator("#internal-chat-market").fill("DE")
                page.locator("#internal-chat-search").click()
                expect(page.locator("#internal-chat-results")).to_contain_text("PRIVATE_FAQ_ANSWER")
                page.locator("#internal-chat-role").select_option("Retailer")
                page.locator("#internal-chat-search").click()
                expect(page.locator("#internal-chat-results")).to_contain_text("Keine freigegebenen")
                page.locator("[data-internal-history]").click()
                expect(page.locator("#internal-history")).to_contain_text("R1")
                page.locator("#internal-history-close").click()
                if os.environ.get("ONESCM_SCREENSHOT_DIR"):
                    Path(os.environ["ONESCM_SCREENSHOT_DIR"]).mkdir(exist_ok=True,parents=True)
                    page.screenshot(path=str(Path(os.environ["ONESCM_SCREENSHOT_DIR"])/"internal-register.png"))
                page.locator("#internal-close").click()
                # Markdown batch UI and real Word formatting.
                page.locator("#markdown-tool").click()
                page.locator("#md-files").set_input_files([
                    {"name":"one.md","mimeType":"text/markdown","buffer":b"# Guide\n\n**Important**\n\n| A | B |\n|---|---|\n| 1 | 2 |"},
                    {"name":"two.md","mimeType":"text/markdown","buffer":b"## Steps\n\n1. Open\n2. Save"}])
                page.locator("#md-mode").select_option("combined")
                with page.expect_download() as info:page.locator("#md-convert").click()
                doc=Document(info.value.path());assert len(doc.tables)==1
                assert any(r.bold for para in doc.paragraphs for r in para.runs)
                page.locator("#md-close").click()
                # Clipboard import of HTML-based Jira/Confluence export.
                page.locator("#sources-button").click()
                page.get_by_text("Quelle aus Zwischenablage anlegen",exact=True).click()
                page.locator("#paste-source-name").fill("Confluence release")
                page.locator("#paste-source-format").select_option("html")
                page.locator("#paste-source-text").fill("<h1>Release 2026.11</h1><p>Retailer contract changes SCM-42.</p>")
                page.locator("#paste-source-save").click()
                expect(page.locator("#source-list")).to_contain_text("Confluence release.html")
                page.locator(".outline-item").filter(has_text="Publishing acceptance").click()
                # Reader suitability, dated controls and evidence editing.
                chapter_time=page.locator(".chapter-validity")
                chapter_time.locator("summary").click()
                chapter_time.locator(".add-validity").click()
                chapter_time.locator('[data-rule="year"]').fill("2026")
                chapter_time.locator('[data-rule="state"]').select_option("Freigegeben")
                panel=page.locator(".publication-panel").first;panel.locator("summary").click()
                panel.locator('[data-use="Releaseletter"]').uncheck()
                panel.locator(".add-validity").click()
                panel.locator('[data-rule="year"]').fill("2026")
                panel.locator('[data-rule="state"]').select_option("Freigegeben")
                page.locator('#profile [data-key="as_of"]').fill("2026-11-03")
                page.locator('#profile [data-key="as_of"]').dispatch_event("change")
                panel.locator(".add-evidence").click()
                for key,value in [("key","SCM-42"),("status","Done"),("type","Story"),("date","2026-11-03")]:panel.locator(f'[data-evidence="{key}"]').fill(value)
                panel.locator('[data-evidence="verified"]').check()
                page.locator('#blocks textarea[data-key="text"]').fill("Open contract now. SCM-42")
                expect(panel.locator('[data-evidence="verified"]')).not_to_be_checked()
                panel.locator('[data-evidence="verified"]').check()
                page.get_by_role("button",name="Speichern",exact=True).click()
                expect(page.locator("#save-state")).to_contain_text("Lokal gespeichert")
                page.locator("#applicability-tool").click()
                expect(page.locator("#applicability-table")).to_contain_text("SCM-42")
                expect(page.locator("#applicability-table")).to_contain_text("Nicht verwendet")
                expect(page.locator("#timeline-table")).to_contain_text("2026-11-03")
                page.locator("#applicability-close").click()
                # Native DOCX template: header retained; sample body removed.
                template=Document();template.sections[0].header.paragraphs[0].text="BRAND HEADER"
                template.add_paragraph("PRIVATE_SAMPLE_BODY")
                raw=io.BytesIO();template.save(raw)
                page.locator("#layout-tool").click()
                page.locator("#layout-name").fill("Brand")
                page.locator("#layout-file").set_input_files({"name":"brand.docx","mimeType":"application/vnd.openxmlformats-officedocument.wordprocessingml.document","buffer":raw.getvalue()})
                page.get_by_role("button",name="Template hochladen",exact=True).click()
                expect(page.locator("#layout-existing")).to_contain_text("Brand")
                page.locator("#layout-docx").select_option(index=1)
                page.locator("#layout-apply").click()
                page.get_by_role("button",name="Speichern",exact=True).click()
                expect(page.locator("#save-state")).to_contain_text("Lokal gespeichert")
                for label,fmt in [("↓ Word","docx"),("↓ PowerPoint","pptx"),("↓ HTML","html"),("↓ PDF","pdf")]:
                    with page.expect_download() as info:page.get_by_role("button",name=label,exact=True).click()
                    raw=Path(info.value.path()).read_bytes()
                    if fmt in ["docx","pptx"]:text=office_parts(raw)
                    elif fmt=="pdf":text=" ".join(p.extract_text() for p in PdfReader(io.BytesIO(raw)).pages)
                    else:text=raw.decode()
                    assert "Open contract now" in text
                    for secret in ["SCM-42","PRIVATE_TESTING_INFO","PRIVATE_FAQ_ANSWER","PRIVATE_SAMPLE_BODY"]:assert secret not in text
                    if fmt=="docx":assert "BRAND HEADER" in text
                # Upload classification is persisted and used by filters/search.
                page.locator("#media-library").click()
                page.locator('#media-upload-meta [data-key="market"]').fill("DE")
                page.locator('#media-upload-meta [data-key="role"]').select_option("HQ")
                page.locator('#media-upload-meta [data-key="division"]').select_option("PC")
                page.locator('#media-upload-meta [data-key="scope"]').select_option("Standard")
                page.locator('#media-upload-meta [data-key="priority"]').select_option("Hoch")
                page.locator('#media-upload-meta [data-key="labels"]').fill("Release, Cockpit")
                page.locator("#media-files").set_input_files({"name":"screen.png","mimeType":"image/png","buffer":sample_image()})
                page.locator("#media-upload").click()
                expect(page.locator("#media-list")).to_contain_text("Priorität Hoch")
                page.locator("#media-search").fill("Cockpit")
                expect(page.locator("#media-list .source-card")).to_have_count(1)
                page.locator('#media-filters [data-filter="role"]').select_option("Retailer")
                expect(page.locator("#media-list")).to_contain_text("keine passenden Bilder")
                page.locator('#media-filters [data-filter="role"]').select_option("HQ")
                page.locator("#media-sort").select_option("priority")
                expect(page.locator("#media-list .source-card")).to_have_count(1)
                page.locator("#media-close").click()
                # Four finalization agents use the saved outline without publishing.
                page.locator("#jobs-button").click()
                expect(page.locator("#job-preset")).to_have_value("final")
                expect(page.locator("#job-agents input:checked")).to_have_count(4)
                page.get_by_role("button",name="Lauf anlegen & starten",exact=True).click()
                expect(page.locator("#job-detail h3")).to_contain_text("completed",timeout=30000)
                expect(page.locator("#job-detail")).to_contain_text("Renderprobe erfolgreich")
                with page.expect_download() as info:page.locator("#job-report-download").click()
                assert "0.4.0" in Path(info.value.path()).read_text()
                assert not errors,errors
                browser.close()
                print("Browser PASS: internal hierarchy/FAQ/revisions/profile isolation, Markdown Word batch, HTML clipboard, Jira recheck, dated suitability, native template, four reader formats and four-agent report.")
        finally:
            server.shutdown();server.server_close();thread.join()


if __name__=="__main__":main()
