"""Browser coverage of domain mapping, private remarks, ingestion and review."""
import io
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright, expect


def main():
    with tempfile.TemporaryDirectory() as directory:
        store = app.Store(Path(directory) / "sources.sqlite3")
        outline = app.new_outline("Handbuch · Mappingtest")
        outline["chapters"] = [app.chapter("Vertrag prüfen"), app.chapter("Details", 2)]
        content = app.block()
        content["text"] = "Freigegebener Beispieltext."
        outline["chapters"][0]["blocks"] = [content]
        outline = store.save(outline)
        server = app.make_server(store, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, executable_path=os.environ.get("ONESCM_BROWSER_PATH"))
                page = browser.new_page(viewport={"width": 1600, "height": 1100})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{server.server_port}")
                page.get_by_role("button", name="Handbuch · Mappingtest", exact=True).click()
                # Central subdomain vocabulary and many-to-many chapter mapping.
                page.get_by_role("button", name="Unterdomänen verwalten", exact=True).click()
                page.locator("#subdomain-parent").select_option("d3")
                page.locator("#subdomain-name").fill("Vertragsprüfung")
                page.get_by_role("button", name="+ Hinzufügen", exact=True).click()
                page.get_by_role("button", name="Unterdomänen speichern", exact=True).click()
                expect(page.locator("#taxonomy-dialog")).not_to_be_visible()
                subdomain = store.taxonomy()["subdomains"][0]["id"]
                for target in ["d3", "d5", subdomain]:
                    page.locator("#mapping-target").select_option(target)
                    page.get_by_role("button", name="Zuordnung hinzufügen", exact=True).click()
                expect(page.locator(".mapping-edge")).to_have_count(3)
                page.locator('#chapter-classification [data-key="keywords"]').fill("Vertrag, Prüfung")
                page.locator('#chapter-classification [data-key="labels"]').fill("Blueprint")
                page.locator('#chapter-classification [data-key="topic"]').fill("Vertragsprozess")
                page.locator("#tree-mode").select_option("domains")
                expect(page.locator('#chapter-tree [data-domain="d3"] > summary')).to_contain_text("1 Kapitel")
                page.locator('.mapping-edge[data-target="d5"] .edge-active').uncheck()
                expect(page.locator('#chapter-tree [data-domain="d5"] > summary')).to_contain_text("0 Kapitel")
                page.locator("#show-inactive-mappings").check()
                expect(page.locator('#chapter-tree [data-domain="d5"] > summary')).to_contain_text("1 Kapitel")
                page.locator("#mapping-enabled").uncheck()
                expect(page.locator("#mapping-summary")).to_contain_text("0 aktive / 3")
                page.locator("#mapping-enabled").check()
                page.locator("#tree-mode").select_option("chapters")
                page.locator("#chapter-tree .chapter-row").filter(has_text="2 Details").count()
                # Add a mapping to a second chapter without implicit inheritance.
                page.locator("#chapter-tree .chapter-row").filter(has_text="1.1 Details").click()
                expect(page.locator(".mapping-edge")).to_have_count(0)
                page.locator("#mapping-target").select_option("d3")
                page.get_by_role("button", name="Zuordnung hinzufügen", exact=True).click()
                page.get_by_role("button", name="Speichern", exact=True).click()
                expect(page.locator("#save-state")).to_contain_text("Lokal gespeichert")
                # Matrix search and role/domain-scoped coloured remarks.
                page.get_by_role("button", name="Kapitel · Rolle · Domäne", exact=True).click()
                page.locator("#matrix-keyword").fill("Prüfung")
                page.locator("#matrix-label").fill("Blueprint")
                page.locator("#matrix-topic").fill("Vertragsprozess")
                page.locator("#matrix-role").select_option("Retailer")
                page.locator("#matrix-domain").select_option("d3")
                expect(page.locator("#matrix-table tbody tr")).to_have_count(1)
                page.get_by_role("button", name="+ Bemerkung", exact=True).click()
                page.locator("#remark-text").fill("SECRET-MATRIX-REMARK")
                page.locator("#remark-color").select_option("violett")
                page.get_by_role("button", name="Bemerkung übernehmen", exact=True).click()
                expect(page.locator("#matrix-table .note-violett")).to_contain_text("SECRET-MATRIX-REMARK")
                page.get_by_role("button", name="Speichern", exact=True).click()
                expect(page.locator("#save-state")).to_contain_text("Lokal gespeichert")
                for name, ext in [("↓ Word", "docx"), ("↓ PowerPoint", "pptx")]:
                    with page.expect_download() as info:
                        page.get_by_role("button", name=name, exact=True).click()
                    file = Path(directory) / f"out.{ext}"
                    info.value.save_as(file)
                    with ZipFile(file) as archive:
                        text = b" ".join(archive.read(n) for n in archive.namelist() if n.endswith(".xml"))
                    assert b"SECRET-MATRIX-REMARK" not in text
                # File import, local triage, explicit review and counts.
                page.locator("#sources-button").click()
                page.locator("#source-files").set_input_files({"name": "Jira-Export.txt", "mimeType": "text/plain", "buffer": "Retailer Vertrag prüfen. Finance Rechnung und Vertragsprüfung für den Markt.".encode()})
                page.locator("#source-kind").select_option("Jira")
                page.get_by_role("button", name="Dateien hochladen", exact=True).click()
                expect(page.locator("#source-list")).to_contain_text("Jira-Export.txt")
                page.get_by_role("button", name="KI Triage", exact=True).click()
                expect(page.locator("#triage-progress")).to_contain_text("1/1 Chunks mit Vorschlägen")
                expect(page.locator("#chunk-list")).to_contain_text("Lokale Regeln (keine KI)")
                page.get_by_role("button", name="Triage-Vorschlag prüfen", exact=True).click()
                page.locator("#review-roles").select_option(["Retailer"])
                page.locator("#review-chapters").select_option([c["id"] for c in outline["chapters"]])
                page.locator("#review-labels").fill("Blueprint, geprüft")
                page.locator("#review-topic").fill("Vertragsprozess")
                page.get_by_role("button", name="Labels & Zuordnungen speichern", exact=True).click()
                expect(page.locator("#chunk-review-dialog")).not_to_be_visible()
                expect(page.locator("#chunk-list")).to_contain_text("2 bestätigte Kapitelzuordnungen")
                page.locator("#chunk-label-search").fill("Blueprint")
                page.locator("#chunk-role-search").select_option("Retailer")
                page.locator("#chunk-topic-search").fill("Vertragsprozess")
                expect(page.locator("#chunk-list .source-card")).to_have_count(1)
                page.locator(".outline-item").filter(has_text="Handbuch · Mappingtest").click()
                expect(page.locator("#chapter-tree .chapter-row").first).to_contain_text("1 Chunks direkt · 1 inkl. Unterkapitel")
                page.locator("#tree-chunk-role").select_option("HQ")
                expect(page.locator("#chapter-tree .chapter-row").first).to_contain_text("0 Chunks direkt")
                page.locator("#tree-chunk-role").select_option("Retailer")
                page.locator("#tree-mode").select_option("domains")
                expect(page.locator('#chapter-tree [data-domain="d3"] > summary')).to_contain_text("2 Kapitel · 1 Chunks")
                page.get_by_role("button", name="Zuklappen", exact=True).click()
                expect(page.locator("#chapter-tree details[open]")).to_have_count(0)
                page.get_by_role("button", name="Aufklappen", exact=True).click()
                screenshot_dir = os.environ.get("ONESCM_SCREENSHOT_DIR")
                if screenshot_dir:
                    Path(screenshot_dir).mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(Path(screenshot_dir) / "mapping.png"), full_page=True)
                # A normal save must keep assignments, and deletion must remove them.
                page.get_by_role("button", name="Speichern", exact=True).click()
                expect(page.locator("#save-state")).to_contain_text("Lokal gespeichert")
                expect(page.locator('#chapter-tree [data-domain="d3"] > summary')).to_contain_text("2 Kapitel · 1 Chunks")
                page.locator("#sources-button").click()
                page.once("dialog", lambda dialog: dialog.accept())
                page.get_by_role("button", name="Datei löschen", exact=True).click()
                expect(page.locator("#source-list")).to_contain_text("Keine passenden Quellen")
                page.locator(".outline-item").filter(has_text="Handbuch · Mappingtest").click()
                expect(page.locator('#chapter-tree [data-domain="d3"] > summary')).to_contain_text("2 Kapitel · 0 Chunks")
                page.reload()
                page.get_by_role("button", name="Handbuch · Mappingtest", exact=True).click()
                page.get_by_role("button", name="Kapitel · Rolle · Domäne", exact=True).click()
                expect(page.locator("#matrix-table")).to_contain_text("SECRET-MATRIX-REMARK")
                assert not errors, errors
                browser.close()
                print("Browser PASS: many-to-many mapping, subdomains, activation, collapsible trees, coloured private matrix notes, filters, upload, rule triage, reviewed assignments, deduplicated role counts, source deletion, persistence and note-free exports.")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    main()
