from pathlib import Path
import os
import sys
import tempfile
import threading
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright, expect

temp = tempfile.TemporaryDirectory()
server = app.make_server(app.Store(Path(temp.name) / "browser.sqlite3"), 0)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=os.environ.get("ONESCM_BROWSER_PATH"))
        page = browser.new_page(viewport={"width": 1512, "height": 1100})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(f"http://127.0.0.1:{server.server_port}")
        page.once("dialog", lambda dialog: dialog.accept("Retailer-Handbuch · Prototyptest"))
        page.get_by_role("button", name="+ Gliederung anlegen").click()
        expect(page.locator("#outline-title")).to_have_value("Retailer-Handbuch · Prototyptest")
        page.get_by_role("button", name="+ Textbaustein zuordnen").click()
        page.locator('.block textarea[data-key="text"]').fill("Öffnen Sie die Vertragsübersicht und wählen Sie den gewünschten Vertrag.")
        page.locator('.block textarea[data-key="note"]').fill("INTERNER-VERMERK-TEST")
        page.locator('.block input[data-key="source"]').fill("Redaktionelles Testbeispiel, keine fachliche oneSCM-Quelle")
        page.get_by_role("button", name="Speichern", exact=True).click()
        expect(page.locator("#save-state")).to_contain_text("Lokal gespeichert")
        page.get_by_role("button", name="Ausgabe prüfen", exact=True).click()
        expect(page.locator("#preview")).to_contain_text("Öffnen Sie die Vertragsübersicht")
        expect(page.locator("#preview")).not_to_contain_text("INTERNER-VERMERK-TEST")
        page.locator('#profile [data-key="role"]').select_option("HQ")
        expect(page.locator("#preview")).not_to_contain_text("INTERNER-VERMERK-TEST")
        page.locator('#profile [data-key="role"]').select_option("Retailer")
        expect(page.locator("#preview")).not_to_contain_text("INTERNER-VERMERK-TEST")
        for button, suffix in [("↓ Word", "docx"), ("↓ PowerPoint", "pptx")]:
            with page.expect_download() as info:
                page.get_by_role("button", name=button, exact=True).click()
            info.value.save_as(str(Path(temp.name) / f"output.{suffix}"))
        page.reload()
        page.locator(".outline-item").filter(has_text="Retailer-Handbuch").first.click()
        expect(page.locator('.block textarea[data-key="text"]')).to_contain_text("Öffnen Sie die Vertragsübersicht")
        page.get_by_role("button", name="Gliederung importieren", exact=True).click()
        page.locator("#import-title").fill("Contract Management · Standard")
        page.locator("#import-text").fill("1 Einleitung\n2 Contract Management\n2.1 Übersicht\n2.2 Bearbeitung\n3 Glossar\n4 FAQ")
        page.get_by_role("button", name="Struktur erkennen", exact=True).click()
        expect(page.locator("#import-preview")).to_contain_text("6 Kapitel erkannt")
        page.get_by_role("button", name="Neue Gliederung übernehmen", exact=True).click()
        expect(page.locator("#chapter-tree .chapter-row")).to_have_count(6)
        page.locator("#chapter-tree .chapter-row").filter(has_text="2.1 Übersicht").click()
        page.get_by_role("button", name="+ Textbaustein zuordnen").click()
        page.locator('.block textarea[data-key="text"]').fill("Beispieltext zur Vertragsübersicht. Fachliche Prüfung steht aus.")
        page.locator('.block [data-key="role"]').select_option("Retailer")
        page.get_by_role("button", name="↓ Nach unten", exact=True).click()
        expect(page.locator("#chapter-tree .chapter-row.selected")).to_contain_text("2.2 Übersicht")
        expect(page.locator('.block textarea[data-key="text"]')).to_contain_text("Beispieltext")
        page.get_by_role("button", name="Speichern", exact=True).click()
        expect(page.locator("#save-state")).to_contain_text("Lokal gespeichert")
        page.screenshot(path=str(Path(temp.name) / "studio.png"), full_page=True)
        page.get_by_role("button", name="Ausgabe prüfen", exact=True).click()
        expect(page.locator("#preview")).to_contain_text("Beispieltext")
        page.locator('#profile [data-key="role"]').select_option("MO")
        expect(page.locator("#preview")).not_to_contain_text("Beispieltext")
        expect(page.locator("#preview")).to_contain_text("Rolle passt nicht")
        assert not errors, errors
        print("Browser PASS: create, save, reload, import preview, subtree move, role filters, note filtering, DOCX and PPTX download. No JavaScript errors.")
        browser.close()
finally:
    server.shutdown()
    server.server_close()
    thread.join()
    temp.cleanup()
