"""Real UI: upload, mask PII, preview, approve, build clickpath, export sanitized pixels."""
from pathlib import Path
import os
import sys
import shutil
import tempfile
import threading
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from test_media import sample_image
from playwright.sync_api import sync_playwright, expect


def main():
    with tempfile.TemporaryDirectory() as directory:
        store = app.Store(Path(directory) / "browser.sqlite3")
        outline = app.new_outline("Medienabnahme")
        outline["chapters"] = [app.chapter("Screens", mandatory=True)]
        store.save(outline)
        server = app.make_server(store, 0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, executable_path=os.environ.get("ONESCM_BROWSER_PATH"))
                page = browser.new_page(viewport={"width": 1700, "height": 1100})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{server.server_port}")
                page.get_by_role("button", name="Medienabnahme", exact=True).click()
                page.get_by_role("button", name="Bilder & Klickstrecken", exact=True).click()
                page.locator("#media-files").set_input_files({"name": "screen.png", "mimeType": "image/png", "buffer": sample_image()})
                page.locator("#media-upload").click()
                expect(page.locator("#media-list")).to_contain_text("PII-Prüfung offen")
                page.locator("[data-edit-asset]").click()
                expect(page.locator("#asset-progress")).to_contain_text("Bereiche markieren")
                page.locator("#asset-caption").fill("Vertragsübersicht")
                page.locator("#asset-note").fill("SECRET_MEDIA_NOTE")
                if shutil.which("tesseract"):
                    accept = lambda dialog: dialog.accept()
                    page.on("dialog", accept)
                    page.locator("#asset-ocr").click()
                    expect(page.locator("#asset-progress")).to_contain_text("visuell prüfen", timeout=60000)
                    expect(page.locator("#asset-ocr-text")).to_contain_text("USERID")
                    page.remove_listener("dialog", accept)
                canvas = page.locator("#asset-canvas")
                canvas.scroll_into_view_if_needed()
                bounds = canvas.bounding_box()
                page.mouse.move(bounds["x"] + bounds["width"] * .02, bounds["y"] + bounds["height"] * .08)
                page.mouse.down()
                page.mouse.move(bounds["x"] + bounds["width"] * .58, bounds["y"] + bounds["height"] * .35)
                page.mouse.up()
                expect(page.locator("#asset-regions")).to_contain_text("PII 1")
                page.locator("#asset-preview").click()
                expect(page.locator("#asset-preview-image")).to_be_visible()
                expect(page.locator("#asset-pii-reviewed")).to_be_enabled()
                page.locator("#asset-pii-reviewed").check()
                page.locator("#asset-status").select_option("Freigegeben")
                page.locator("#asset-save").click()
                expect(page.locator("#media-list")).to_contain_text("PII-Prüfung bestätigt")
                asset = store.media.listing()[0]
                page.locator("#media-create-path").click()
                page.locator("#media-assignment-title").fill("Vertrag anlegen")
                page.locator('#media-frames [data-frame="0"] select').select_option(f"{asset['id']}|2")
                page.locator("#media-add-frame").click()
                page.locator('#media-frames [data-frame="1"] select').select_option(f"{asset['id']}|2")
                page.locator('#media-frames [data-frame="1"] textarea').fill("Schritt abschließen")
                page.locator("#media-assignment-note").fill("SECRET_ASSIGNMENT_NOTE")
                page.get_by_role("button", name="Medienzuordnung übernehmen", exact=True).click()
                expect(page.locator("#chapter-media")).to_contain_text("Klickstrecke · 2 Positionen")
                page.get_by_role("button", name="Speichern", exact=True).click()
                expect(page.locator("#save-state")).to_contain_text("Lokal gespeichert")
                page.get_by_role("button", name="Ausgabe prüfen", exact=True).click()
                expect(page.locator("#preview figure img")).to_have_count(2)
                expect(page.locator("#preview")).to_contain_text("Schritt 2: Schritt abschließen")
                expect(page.locator("#preview")).not_to_contain_text("SECRET_")
                expect(page.locator("#preview")).not_to_contain_text("[Inhalt ergänzen]")
                screenshots = os.environ.get("ONESCM_SCREENSHOT_DIR")
                if screenshots:
                    Path(screenshots).mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(Path(screenshots) / "media-preview.png"), full_page=True)
                for button, fmt in [("↓ Word", "docx"), ("↓ PowerPoint", "pptx")]:
                    with page.expect_download() as info:
                        page.get_by_role("button", name=button, exact=True).click()
                    path = Path(directory) / ("output."+fmt)
                    info.value.save_as(str(path))
                    with zipfile.ZipFile(path) as archive:
                        blobs = [archive.read(n) for n in archive.namelist() if "/media/" in n]
                        assert store.media.image(asset["id"], 2, "Retailer") in blobs
                        assert store.media.original(asset["id"]) not in blobs
                assert not errors, errors
                browser.close()
                print("Browser PASS: image upload, drawn PII mask, visual approval, two-step clickpath, caption override, preview and sanitized DOCX/PPTX assets.")
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


if __name__ == "__main__":
    main()
