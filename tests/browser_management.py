"""End-to-end coverage for outline metadata, manual hierarchy and comparison."""
from pathlib import Path
import os
import re
import sys
import tempfile
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright, expect


def main():
    with tempfile.TemporaryDirectory() as directory:
        store = app.Store(Path(directory) / "browser.sqlite3")
        server = app.make_server(store, 0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, executable_path=os.environ.get("ONESCM_BROWSER_PATH"))
                page = browser.new_page(viewport={"width": 1600, "height": 1100})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{server.server_port}")
                expect(page.locator("#overview")).to_be_visible()
                page.once("dialog", lambda dialog: dialog.accept("Retailer-Handbuch"))
                page.get_by_role("button", name="+ Gliederung anlegen", exact=True).click()
                expect(page.locator("#outline-title")).to_have_value("Retailer-Handbuch")
                page.locator('#outline-metadata [data-key="version"]').fill("1.1")
                page.locator('#outline-metadata [data-key="owner"]').fill("Dokumentation")
                page.locator('#outline-metadata [data-key="tags"]').fill("Blueprint, Van")
                page.locator('#outline-metadata [data-key="description"]').fill("Manuell gepflegte Struktur")

                def add(title, child=False):
                    page.get_by_role("button", name="+ Unterkapitel erstellen" if child else "+ Kapitel erstellen", exact=True).click()
                    page.locator("#new-chapter-title").fill(title)
                    page.get_by_role("button", name="Kapitel anlegen", exact=True).click()
                    expect(page.locator("#chapter-title")).to_have_value(title)

                add("Vertragsverwaltung")
                add("Prüfung", child=True)
                page.get_by_role("button", name="+ Textbaustein zuordnen").click()
                page.locator('.block textarea[data-key="text"]').fill("Dieser Text muss beim Verschieben erhalten bleiben.")
                expect(page.locator("#chapter-tree .folder-tree .folder-tree")).to_have_count(1)
                page.get_by_role("button", name="Zuklappen", exact=True).click()
                expect(page.locator(".chapter-row").filter(has_text="Prüfung")).not_to_be_visible()
                page.get_by_role("button", name="Aufklappen", exact=True).click()
                expect(page.locator(".chapter-row").filter(has_text="Prüfung")).to_be_visible()
                page.get_by_role("button", name="Speichern", exact=True).click()
                expect(page.locator("#save-state")).to_contain_text("Lokal gespeichert")
                page.reload()
                expect(page.locator("#overview-rows")).to_contain_text("1.1")
                expect(page.locator("#overview-rows")).to_contain_text("Dokumentation")
                page.get_by_role("button", name="Retailer-Handbuch", exact=True).click()
                expect(page.locator('#outline-metadata [data-key="description"]')).to_have_value("Manuell gepflegte Struktur")
                page.get_by_role("button", name="Kopieren", exact=True).click()
                expect(page.locator("#outline-title")).to_have_value("Retailer-Handbuch – Kopie")
                page.locator('#outline-metadata [data-key="version"]').fill("2.0")
                page.locator('#outline-metadata [data-key="status"]').select_option("In Prüfung")
                page.locator(".chapter-row").filter(has_text="Vertragsverwaltung").click()
                page.locator("#chapter-title").fill("Serviceverträge")
                page.locator(".chapter-row").filter(has_text="Prüfung").click()
                page.get_by_role("button", name="← Höhere Ebene", exact=True).click()
                expect(page.locator('.block textarea[data-key="text"]')).to_have_value("Dieser Text muss beim Verschieben erhalten bleiben.")
                add("Zusatz")
                page.locator(".chapter-row").filter(has_text="FAQ").click()
                page.once("dialog", lambda dialog: dialog.accept())
                page.locator('[data-action="delete"]').click()
                page.get_by_role("button", name="Speichern", exact=True).click()
                expect(page.locator("#save-state")).to_contain_text("Lokal gespeichert")
                page.get_by_role("button", name="Alle Gliederungen", exact=True).click()
                expect(page.locator("#overview-rows tr")).to_have_count(2)
                page.locator("#overview-search").fill("Blueprint")
                expect(page.locator("#overview-rows .compare-choice")).to_have_count(2)
                page.locator("#overview-status").select_option("In Prüfung")
                expect(page.locator("#overview-rows .compare-choice")).to_have_count(1)
                page.locator("#overview-status").select_option("")
                page.locator("#overview-rows .compare-choice").nth(0).check()
                page.locator("#overview-rows .compare-choice").nth(1).check()
                page.get_by_role("button", name="Auswahl vergleichen (2/2)").click()
                expect(page.locator(".comparison-columns")).to_be_visible()
                expect(page.locator(".diff-summary")).to_contain_text("1 Umbenannt")
                expect(page.locator(".diff-summary")).to_contain_text("1 Verschoben")
                expect(page.locator(".diff-summary")).to_contain_text("1 Neu")
                expect(page.locator(".diff-summary")).to_contain_text("1 Entfernt")
                expect(page.locator(".metadata-diff")).to_contain_text("Gliederungsversion")
                page.get_by_role("button", name="Alle zuklappen", exact=True).click()
                expect(page.locator(".comparison-tree details[open]")).to_have_count(0)
                page.get_by_role("button", name="Alle aufklappen", exact=True).click()
                page.locator(".compare-node").filter(has_text="Serviceverträge").click()
                expect(page.locator(".matched-node")).to_have_count(2)
                page.locator("#differences-only").check()
                expect(page.locator(".comparison-columns .diff-tag.diff-unchanged")).to_have_count(0)
                screenshot_dir = os.environ.get("ONESCM_SCREENSHOT_DIR")
                if screenshot_dir:
                    Path(screenshot_dir).mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(Path(screenshot_dir) / "comparison.png"), full_page=True)
                # History can compare two saved revisions of the same outline.
                page.locator(".outline-item").filter(has_text="Retailer-Handbuch – Kopie").click()
                page.get_by_role("button", name="Gespeicherte Stände vergleichen", exact=True).click()
                expect(page.locator("#compare-left-revision")).to_have_value("1")
                expect(page.locator("#compare-right-revision")).to_have_value("2")
                expect(page.locator(".diff-summary")).to_contain_text("1 Umbenannt")
                # Leaving the editor for the overview does not discard unsaved metadata.
                page.locator(".outline-item").filter(has_text="Retailer-Handbuch – Kopie").click()
                page.locator('#outline-metadata [data-key="owner"]').fill("Noch nicht gespeichert")
                page.get_by_role("button", name="Alle Gliederungen", exact=True).click()
                page.locator(".outline-item").filter(has_text="Retailer-Handbuch – Kopie").click()
                expect(page.locator('#outline-metadata [data-key="owner"]')).to_have_value("Noch nicht gespeichert")
                assert not errors, errors
                browser.close()
                print("Browser PASS: metadata persistence, chapter/subchapter creation, collapsible trees, copy lineage, overview filters, two-outline and historical comparison, counterpart highlighting, unsaved edit preservation.")
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


if __name__ == "__main__":
    main()
