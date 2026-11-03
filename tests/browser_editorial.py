"""Browser acceptance: safe reimport, reusable content, release and provenance."""
from pathlib import Path
import os
import sys
import tempfile
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright, expect


def main():
    with tempfile.TemporaryDirectory() as directory:
        store = app.Store(Path(directory) / "browser.sqlite3")
        outline = app.new_outline("Abnahme")
        outline["chapters"] = [app.chapter("Verträge", mandatory=True), app.chapter("FAQ", mandatory=True)]
        for c in outline["chapters"]:
            c["blocks"] = [dict(app.block(), text="Vorhandener Inhalt " + c["title"], status="Freigegeben")]
        outline = store.save(outline)
        original_id = outline["chapters"][0]["id"]
        entry = store.library.save({"id": app.uid(), "revision": 0, "title": "Wichtiger Hinweis",
                                   "block": dict(app.block(), text="Zentrale Anleitung", status="Freigegeben")})
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
                page.get_by_role("button", name="Abnahme", exact=True).click()
                page.get_by_role("button", name="Gliederung importieren", exact=True).click()
                page.locator("#import-target").select_option(outline["id"])
                page.locator("#import-text").fill("1 Serviceverträge")
                page.get_by_role("button", name="Struktur erkennen", exact=True).click()
                page.locator("#apply-import").click()
                expect(page.locator("#reimport-review")).to_contain_text("FAQ")
                page.locator("[data-import-id]").select_option(original_id)
                page.locator("#apply-import").click()
                expect(page.locator("#reimport-review")).to_contain_text("Umbenannt: 1")
                page.locator("#apply-import").click()
                expect(page.locator("#chapter-title")).to_have_value("Serviceverträge")
                expect(page.locator('.block textarea[data-key="text"]')).to_have_value("Vorhandener Inhalt Verträge")
                expect(page.locator("#chapter-tree")).to_contain_text("FAQ")
                assert store.get(outline["id"])["chapters"][0]["id"] == original_id

                page.get_by_role("button", name="Inhalte zuordnen", exact=True).click()
                expect(page.locator("#library-list")).to_contain_text("Wichtiger Hinweis")
                page.locator("[data-assign]").click()
                expect(page.locator(".block")).to_have_count(2)
                expect(page.locator('.block').nth(1).locator('textarea[data-key="text"]')).to_be_disabled()
                page.locator('.block').nth(1).get_by_text("Gültigkeit dieser Zuordnung weiter einschränken", exact=True).click()
                page.locator('.block').nth(1).locator('[data-restrict="market"]').fill("DE")
                page.get_by_role("button", name="Speichern", exact=True).click()
                expect(page.locator("#save-state")).to_contain_text("Lokal gespeichert")
                page.get_by_role("button", name="Ausgabe prüfen", exact=True).click()
                expect(page.locator("#preview")).not_to_contain_text("Zentrale Anleitung")
                page.get_by_role("button", name="Struktur & Inhalte", exact=True).click()
                page.locator('#profile [data-key="market"]').fill("DE")
                page.locator('#profile [data-key="market"]').blur()
                page.locator("#chapter-config summary").click()
                page.locator('#chapter-config [data-language="de"]').fill("Vertragsbearbeitung")
                page.locator('#chapter-config [data-key="status"]').select_option("Freigegeben")
                page.locator(".chapter-row").filter(has_text="FAQ").click()
                page.locator("#chapter-config summary").click()
                page.locator('#chapter-config [data-key="status"]').select_option("Freigegeben")
                page.get_by_role("button", name="Profil prüfen & freigeben", exact=True).click()
                expect(page.locator('#outline-metadata [data-key="status"]')).to_have_value("Freigegeben")
                page.locator("#publish-output").check()
                with page.expect_download() as download_info:
                    page.get_by_role("button", name="↓ Word", exact=True).click()
                download = download_info.value
                download.save_as(str(Path(directory) / "output.docx"))
                page.get_by_role("button", name="Verwendungsnachweis", exact=True).click()
                expect(page.locator("#usage-content")).to_contain_text("Freigegeben")
                expect(page.locator("#usage-content")).to_contain_text("onescm-office-2")
                with page.expect_download() as old_download:
                    page.locator("[data-download]").click()
                old_download.value.save_as(str(Path(directory) / "original.docx"))
                assert (Path(directory) / "output.docx").read_bytes() == (Path(directory) / "original.docx").read_bytes()
                page.get_by_role("button", name="Schließen", exact=True).click()
                page.locator("#outline-title").fill("Abnahme überarbeitet")
                page.get_by_role("button", name="Speichern", exact=True).click()
                expect(page.locator('#outline-metadata [data-key="status"]')).to_have_value("Entwurf")
                page.get_by_role("button", name="Inhalte zuordnen", exact=True).click()
                page.locator("[data-translate-entry]").click()
                page.locator("#library-title").fill("Important note")
                page.locator("#library-text").fill("Central instructions")
                page.locator('#library-block-fields [data-key="language"]').select_option("en")
                page.locator('#library-block-fields [data-key="status"]').select_option("Freigegeben")
                page.locator("#translation-reviewed").check()
                page.get_by_role("button", name="Bausteinrevision speichern", exact=True).click()
                expect(page.locator("#library-list")).to_contain_text("Important note")
                translated = next(e for e in store.library.listing() if e["title"] == "Important note")
                assert translated["translation"]["source_revision"] == 1
                page.locator(f'[data-library-edit="{entry["id"]}"]').click()
                page.locator("#library-text").fill("Zentrale Anleitung überarbeitet")
                page.get_by_role("button", name="Bausteinrevision speichern", exact=True).click()
                expect(page.locator("#library-list")).to_contain_text("Ausgangsbaustein wurde geändert")
                assert not errors, errors
                browser.close()
                print("Browser PASS: safe reimport, pinned content, narrowed validity, release and original downloads, draft revisions, reviewed translation and stale-source warning.")
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


if __name__ == "__main__":
    main()
