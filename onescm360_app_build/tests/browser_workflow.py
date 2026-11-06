"""End-to-end browser workflow (Playwright). Run: python tests/browser_workflow.py

Optional: ONESCM_BROWSER_PATH=<chromium binary>, ONESCM_SCREENSHOTS=<folder>.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import CH01_HTML, ROOT, html_doc, make_docx, p  # noqa: E402

from playwright.sync_api import expect, sync_playwright  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402

from app import create_app  # noqa: E402


def _png_1x1() -> bytes:
    import struct
    import zlib

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    header = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(b"\x00\x0b\x6e\x8a\xff")) + chunk(b"IEND", b"")


PNG = _png_1x1()


class SlowImport:
    """WSGI middleware that delays /api/import so the loading state is observable."""

    def __init__(self, app, delay=1.2):
        self.app, self.delay = app, delay

    def __call__(self, environ, start_response):
        if environ.get("PATH_INFO") == "/api/import":
            time.sleep(self.delay)
        return self.app(environ, start_response)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="onescm360-browser-"))
    onedrive = tmp / "OneDrive - Test (tenant)" / "-oneSCM360"
    onedrive.mkdir(parents=True)
    shutil.copy(ROOT / "rules.json", tmp / "rules.json")
    flask_app = create_app({"DATA_DIR": tmp / "data", "RULES_PATH": tmp / "rules.json", "ONEDRIVE_ROOT": str(onedrive)})
    server = make_server("127.0.0.1", 0, SlowImport(flask_app), threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}"
    shots = os.environ.get("ONESCM_SCREENSHOTS")
    errors: list[str] = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, executable_path=os.environ.get("ONESCM_BROWSER_PATH") or None)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
            # Expected 4xx answers are logged by Chromium as "Failed to load resource"; everything else
            # (CSP violations, script errors) counts as a failure.
            page.on("console", lambda m: errors.append(f"console: {m.text}")
                    if m.type == "error" and not m.text.startswith("Failed to load resource") else None)

            def shot(name):
                if shots:
                    Path(shots).mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(Path(shots) / f"{name}.png"), full_page=True)

            page.goto(url)
            # --- navigation: all registers permanently visible, active one highlighted
            names = ["Dashboard", "Import", "Regelwerk", "Claims", "Evidence", "Tabellen", "Coverage", "Synchronisation", "Dokumentation"]
            for name in names:
                expect(page.locator("#tabs").get_by_role("button", name=name, exact=True)).to_be_visible()
            expect(page.locator('#tabs button[data-tab="dashboard"]')).to_have_class(re.compile("active"))
            expect(page.locator('[data-kpi="imports"] .value')).to_have_text("0")

            # --- import: files are checked on selection; invalid ones never reach the import
            page.locator('#tabs button[data-tab="import"]').click()
            expect(page.locator('#tabs button[data-tab="import"]')).to_have_attribute("aria-current", "page")
            expect(page.locator('#tabs button[data-tab="dashboard"]')).not_to_have_class(re.compile("active"))
            page.locator("#imp-submit").click()
            expect(page.locator("#imp-error")).to_have_text("Bitte eine Datei auswählen.")
            queue_row = lambda name: page.locator("#imp-queue tbody tr", has_text=name)
            page.locator("#imp-file").set_input_files({"name": "notizen.txt", "mimeType": "text/plain", "buffer": b"x"})
            expect(queue_row("notizen.txt")).to_contain_text("nicht unterstützt")
            page.locator("#imp-file").set_input_files({"name": "leer.html", "mimeType": "text/html", "buffer": b""})
            expect(queue_row("leer.html")).to_contain_text("Die Datei ist leer.")
            page.locator("#imp-file").set_input_files({"name": "kaputt.docx", "mimeType": "application/octet-stream", "buffer": b"PK\x03\x04kaputt"})
            expect(queue_row("kaputt.docx")).to_contain_text("beschädigt")
            page.locator("#imp-submit").click()
            expect(page.locator("#imp-error")).to_contain_text("notizen.txt: Dateityp")
            expect(page.locator("#imp-error")).to_contain_text("kaputt.docx: Die DOCX-Datei ist beschädigt")
            expect(page.locator("#imp-progress")).to_be_hidden()
            page.locator("#imp-clear").click()
            expect(page.locator("#imp-queue-card")).to_be_hidden()

            # --- import: server-side error, hourglass always disappears
            page.locator("#imp-file").set_input_files({"name": "CH01_ohne_fragen.html", "mimeType": "text/html", "buffer": html_doc(p("Nur Text ohne Fragekennung."))})
            expect(queue_row("CH01_ohne_fragen.html")).to_contain_text("BEREIT")
            expect(queue_row("CH01_ohne_fragen.html").locator('select[aria-label="Kapitel"]')).to_have_value("CH01")
            expect(queue_row("CH01_ohne_fragen.html")).to_contain_text("erkannt: Dateiname")
            page.locator("#imp-submit").click()
            expect(page.locator("#imp-progress")).to_be_visible()
            expect(page.locator("#imp-submit")).to_be_disabled()
            expect(page.locator("#imp-error")).to_contain_text("Keine Fragen 01-F01 bis 01-F20")
            expect(page.locator("#imp-progress")).to_be_hidden()
            expect(page.locator("#imp-submit")).to_be_enabled()
            expect(queue_row("CH01_ohne_fragen.html")).to_contain_text("FEHLER")
            page.locator("#imp-clear").click()

            # --- import: single file success
            page.locator("#imp-file").set_input_files({"name": "ch01.html", "mimeType": "text/html", "buffer": CH01_HTML})
            expect(queue_row("ch01.html")).to_contain_text("BEREIT")
            page.locator("#imp-submit").click()
            expect(page.locator("#imp-progress")).to_be_visible()
            expect(page.locator("#imp-status-text")).to_contain_text("Analyse")
            expect(page.locator("#imp-submit")).to_be_disabled()
            expect(page.locator("#imp-result-id")).to_have_text(re.compile(r"^IMP-\d{8}-\d{6}-[A-F0-9]{6}$"))
            expect(page.locator("#imp-progress")).to_be_hidden()
            expect(page.locator("#imp-submit")).to_be_enabled()
            expect(page.locator("#imp-error")).to_be_hidden()
            expect(page.locator("#imp-result-questions")).to_have_text("4 von 20 beantwortet")
            expect(page.locator("#imp-result-tables")).to_have_text("2")
            expect(page.locator("#imp-findings")).to_contain_text("oneSCM")
            expect(queue_row("ch01.html")).to_contain_text("IMPORTIERT")

            # --- multi import: three files, classified and grouped by language, role, chapter, domain
            page.locator("#imp-file").set_input_files([
                {"name": "CH02_Dealer_Contract-Management_DE.html", "mimeType": "text/html",
                 "buffer": html_doc(p("02-F01 Der Dealer legt Verträge im Portal an und prüft die Laufzeit."))},
                {"name": "CH03_Market-Operations_Finance_EN.html", "mimeType": "text/html",
                 "buffer": html_doc(p("03-F01 Market Operations creates the invoice for the dealer and checks the payment."))},
                {"name": "Antworten_Kapitel_2_Market-Setting_EN.docx", "mimeType": "application/octet-stream",
                 "buffer": make_docx(["02-F02 The market configuration is maintained per country by the team."], media={"image1.png": PNG})},
            ])
            expect(page.locator("#imp-queue tbody tr", has_text="BEREIT")).to_have_count(3)
            expect(page.locator("#imp-submit")).to_have_text("3 Dateien importieren")
            expect(queue_row("CH03_Market").locator('select[aria-label="Rolle"]')).to_have_value("MO")
            expect(queue_row("CH03_Market").locator('select[aria-label="Domäne"]')).to_have_value("finance-management")
            expect(queue_row("CH03_Market").locator('select[aria-label="Sprache"]')).to_have_value("EN")
            expect(queue_row("Antworten_Kapitel_2").locator('select[aria-label="Kapitel"]')).to_have_value("CH02")
            expect(queue_row("Antworten_Kapitel_2").locator('select[aria-label="Domäne"]')).to_have_value("market-setting")
            group_rows = page.locator("#imp-queue tbody tr.group-row")
            expect(group_rows.first).to_contain_text("Kapitel: CH01")
            page.locator("#imp-group").select_option("role")
            # ch01.html names the Dealer far more often than Market Operations → Dealer
            expect(group_rows).to_have_text(["Rolle: Alle Rollen (1)", "Rolle: Dealer (2)", "Rolle: MO (Market Operations) (1)"])
            page.locator("#imp-group").select_option("language")
            expect(group_rows).to_have_text(["Sprache: DE (2)", "Sprache: EN (2)"])
            page.locator("#imp-group").select_option("domain")
            expect(group_rows).to_have_text(["Domäne: Contract Management (1)", "Domäne: Finance Management (1)", "Domäne: Market Setting (1)", "Domäne: Ohne Domäne (1)"])
            queue_row("Antworten_Kapitel_2").locator('select[aria-label="Rolle"]').select_option("HQ")
            expect(queue_row("Antworten_Kapitel_2")).to_contain_text("manuell")
            expect(queue_row("Antworten_Kapitel_2").locator('select[aria-label="Rolle"] option')).to_have_text(
                ["Alle Rollen", "Dealer", "MO (Market Operations)", "HQ", "Market", "IT", "intern"])
            page.locator("#imp-group").select_option("chapterId")
            expect(group_rows).to_have_text(["Kapitel: CH01 – Grundlagen und Überblick (1)", "Kapitel: CH02 – Kapitel 02 (2)", "Kapitel: CH03 – Kapitel 03 (1)"])
            page.locator("#imp-submit").click()
            expect(page.locator("#imp-status-text")).to_contain_text("von 3")
            expect(page.locator("#imp-batch-result")).to_have_text("3 von 3 Dateien importiert.")
            expect(page.locator("#imp-progress")).to_be_hidden()
            expect(page.locator("#imp-queue tbody tr", has_text="IMPORTIERT")).to_have_count(4)
            expect(page.locator("#imp-result-scope")).to_have_text(re.compile("Dealer|MO|HQ|Alle Rollen"))
            shot("02b-multi-import")
            expect(page.locator("#imp-media img")).to_have_count(1)
            page.locator("#imp-media img").scroll_into_view_if_needed()  # thumbnails load lazily
            page.wait_for_function("() => { const i = document.querySelector('#imp-media img'); return i && i.complete && i.naturalWidth === 1; }")
            queue_row("ch01.html").get_by_role("button", name="Ergebnis").click()
            expect(page.locator("#imp-summary")).to_contain_text("BLOCKED")
            shot("02-import")
            page.locator('#tabs button[data-tab="coverage"]').click()
            expect(page.locator("#cov-gate")).to_have_text("BLOCKED")
            expect(page.locator("#cov-blockers")).to_contain_text("Kritischer Claim ohne direkte Evidence")

            # --- rule set CRUD
            page.locator('#tabs button[data-tab="rules"]').click()
            expect(page.locator("#rules-table tbody tr")).to_have_count(6)
            page.locator("#rule-category").select_option("synonym")
            page.locator("#rule-source").fill("Händler")
            page.locator("#rule-target").fill("Dealer")
            page.get_by_role("button", name="Regel anlegen").click()
            row = page.locator("#rules-table tbody tr", has_text="Händler")
            expect(row).to_have_count(1)
            page.locator("#rule-source").fill("händler")
            page.locator("#rule-target").fill("Dealer")
            page.get_by_role("button", name="Regel anlegen").click()
            expect(page.locator("#toast")).to_contain_text("existiert bereits")
            row.get_by_role("button", name="Bearbeiten").click()
            edit_row = page.locator("#rules-table tbody tr").filter(has=page.locator('input[aria-label="Ziel"]'))
            edit_row.locator('input[aria-label="Ziel"]').fill("Händler (Dealer)")
            edit_row.get_by_role("button", name="Abbrechen").click()
            expect(page.locator("#rules-table tbody tr", has_text="Händler")).to_contain_text("Dealer")
            page.locator("#rules-table tbody tr", has_text="Händler").get_by_role("button", name="Bearbeiten").click()
            edit_row.locator('input[aria-label="Ziel"]').fill("Dealer (DE)")
            edit_row.get_by_role("button", name="Speichern").click()
            expect(page.locator("#rules-table tbody tr", has_text="Händler")).to_contain_text("Dealer (DE)")
            page.locator("#rule-filter button", has_text="Synonyme").click()
            expect(page.locator("#rules-table tbody tr")).to_have_count(2)
            page.locator("#rule-preview-text").fill("Der Händler nutzt onescm.")
            page.locator("#rule-preview").click()
            expect(page.locator("#rule-preview-out")).to_contain_text("Der Dealer (DE) nutzt oneSCM.")
            page.once("dialog", lambda d: d.dismiss())
            page.locator("#rules-table tbody tr", has_text="Händler").get_by_role("button", name="Löschen").click()
            expect(page.locator("#rules-table tbody tr", has_text="Händler")).to_have_count(1)
            page.once("dialog", lambda d: d.accept())
            page.locator("#rules-table tbody tr", has_text="Händler").get_by_role("button", name="Löschen").click()
            expect(page.locator("#rules-table tbody tr", has_text="Händler")).to_have_count(0)
            shot("03-rules")

            # --- chapter editor (question catalogues CH02-CH16)
            page.locator('#tabs button[data-tab="chapters"]').click()
            page.locator("#chap-select").select_option("CH05")
            expect(page.locator("#chap-origin")).to_contain_text("STANDARD")
            expect(page.locator("#chap-questions tbody tr")).to_have_count(20)
            page.locator("#chap-title").fill("Vertragsverwaltung")
            page.locator('#chap-roles input[value="HQ"]').check()
            page.locator('input[aria-label="Titel 05-F01"]').fill("Welche Vertragsarten gibt es?")
            page.locator('select[aria-label="Kritikalität 05-F01"]').select_option("CRITICAL")
            page.locator("#chap-save").click()
            expect(page.locator("#chap-saved")).to_contain_text("CH05 gespeichert")
            expect(page.locator("#chap-origin")).to_contain_text("ANGEPASST")
            expect(page.locator('#cov-chapter option[value="CH05"]')).to_have_text("CH05 – Vertragsverwaltung (Schema-Entwurf)")
            page.locator("#chap-csv").set_input_files({"name": "katalog.csv", "mimeType": "text/csv",
                                                       "buffer": "Frage;Titel;Kritikalität\r\nF02;Wer darf Verträge ändern?;hoch\r\n".encode("utf-8")})
            expect(page.locator("#chap-csv-loaded")).to_contain_text("Noch nichts gespeichert")
            expect(page.locator('input[aria-label="Titel 05-F02"]')).to_have_value("Wer darf Verträge ändern?")
            page.locator("#chap-cancel").click()
            expect(page.locator('input[aria-label="Titel 05-F02"]')).to_have_value("Frage 05-F02")
            expect(page.locator('input[aria-label="Titel 05-F01"]')).to_have_value("Welche Vertragsarten gibt es?")
            page.locator("#chap-title").fill("")
            page.locator("#chap-save").click()
            expect(page.locator("#chap-error")).to_contain_text("Kapiteltitel")
            page.once("dialog", lambda d: d.accept())
            page.locator("#chap-reset").click()
            expect(page.locator("#chap-origin")).to_contain_text("STANDARD")
            expect(page.locator("#chap-title")).to_have_value("Kapitel 05")
            shot("03b-chapters")

            # --- claims review
            page.locator('#tabs button[data-tab="claims"]').click()
            page.locator("#claim-chapter").select_option("CH01")
            expect(page.locator("#claims-table tbody tr.clickable").first).to_be_visible()
            page.locator("#claims-table tbody tr", has_text="möglicherweise").click()
            expect(page.locator("#claim-editor")).to_be_visible()
            page.locator("#claim-confirm").click()
            expect(page.locator("#toast")).to_contain_text("Unsichere")
            target = page.locator("#claims-table tbody tr", has_text="Der Dealer darf Aufträge stornieren")
            target_id = target.get_attribute("data-claim-id")
            target.click()
            expect(page.locator("#claim-editor")).to_have_attribute("data-claim-id", target_id)
            expect(page.locator('#claim-form [data-field="canonicalStatement"]')).to_have_value("Der Dealer darf Aufträge stornieren.")
            page.locator("#evidence-new select").first.select_option("JIRA")
            page.locator('#evidence-new input[placeholder="z. B. ONESCM-123"]').fill("ONESCM-9")
            page.get_by_role("button", name="Evidence zuordnen").click()
            expect(page.locator("#claim-editor")).to_contain_text("ONESCM-9")
            page.locator('#claim-form [data-field="reviewNote"]').fill("Geprüft im Fachreview")
            page.locator("#claim-confirm").click()
            expect(page.locator("#claims-table tbody tr", has_text="Der Dealer darf Aufträge stornieren")).to_contain_text("CONFIRMED")
            page.locator("#claim-new-box summary").click()
            page.locator("#claim-new-question").select_option("01-F10")
            page.locator("#claim-new-text").fill("Market Operations darf Preise nur nach Freigabe ändern.")
            page.locator("#claim-new").get_by_role("button", name="Claim anlegen").click()
            expect(page.locator("#claims-table tbody tr", has_text="Preise nur nach Freigabe")).to_have_count(1)
            page.once("dialog", lambda d: d.accept())
            page.locator("#claim-delete").click()
            expect(page.locator("#claims-table tbody tr", has_text="Preise nur nach Freigabe")).to_have_count(0)
            shot("04-claims")

            # --- evidence
            page.locator('#tabs button[data-tab="evidence"]').click()
            jira_row = page.locator("#evidence-table tbody tr", has_text="ONESCM-9")
            jira_row.locator('select[aria-label="Evidence-Stufe"]').select_option("DIRECT_VALIDATED")
            jira_row.locator('select[aria-label="Evidence-Status"]').select_option("VALIDATED")
            jira_row.get_by_role("button", name="Speichern").click()
            expect(page.locator("#evidence-table tbody tr", has_text="ONESCM-9")).to_contain_text("1,00")

            # --- tables
            page.locator('#tabs button[data-tab="tables"]').click()
            first = page.locator('#tables-table tbody tr[data-table-id="TBL-CH01-001"]')
            expect(first).to_contain_text("REVIEW")
            first.locator('select[aria-label="Quellfrage"]').select_option("01-F01")
            expect(page.locator('#tables-table tbody tr[data-table-id="TBL-CH01-001"]')).not_to_contain_text("REVIEW")
            page.locator('#tables-table tbody tr[data-table-id="TBL-CH01-002"]').get_by_role("button", name="Ansehen").click()
            expect(page.locator("#tbl-preview-table thead")).to_contain_text("Größe")
            with page.expect_download() as download:
                page.locator('#tables-table tbody tr[data-table-id="TBL-CH01-002"] a', has_text="CSV").click()
            assert download.value.suggested_filename == "TBL-CH01-002.csv"

            # --- coverage
            page.locator('#tabs button[data-tab="coverage"]').click()
            # The only critical claim was confirmed with validated Jira evidence above, so the
            # hard blocker from the import is gone and the gate follows the score.
            expect(page.locator("#cov-gate")).to_have_text(re.compile("REVIEW|INCOMPLETE|STARTED"))
            expect(page.locator("#cov-dims .kpi")).to_have_count(6)
            expect(page.locator("#cov-blockers")).to_have_text("Keine Hard Blocker.")
            expect(page.locator("#cov-roles tbody")).to_contain_text("Dealer")
            page.locator("#cov-chapter").select_option("CH05")
            expect(page.locator("#cov-gate")).to_have_text("NOT_STARTED")
            shot("05-coverage")

            # --- synchronisation: folder connection and export
            page.locator('#tabs button[data-tab="sync"]').click()
            expect(page.locator("#sync-local-status")).to_contain_text("READY_FOR_CLIENT")
            expect(page.locator("#sync-status")).to_contain_text("NOT_VERIFIABLE_WITHOUT_GRAPH")
            page.locator("#sync-path").fill(str(tmp / "fehlt"))
            page.get_by_role("button", name="Pfad speichern & prüfen").click()
            expect(page.locator("#sync-local-status")).to_contain_text("PATH_MISSING")
            page.locator("#sync-export").click()
            expect(page.locator("#sync-result")).to_contain_text("PATH_MISSING")
            page.locator("#sync-reset").click()
            expect(page.locator("#sync-local-status")).to_contain_text("READY_FOR_CLIENT")
            page.locator("#sync-chapter").select_option("CH01")
            page.locator("#sync-export").click()
            expect(page.locator("#sync-export-ok")).to_contain_text("Paket: 06_Exports/Packages/CH01_")
            assert any((onedrive / "06_Exports" / "Packages").glob("CH01_*_upload.zip"))
            shot("06-sync")

            # --- manual versions (Handbuchstand) and rule-based cleanup
            page.locator("#man-chapter").select_option("CH01")
            page.locator("#man-stage").select_option("Released")
            page.locator("#man-preview").click()
            expect(page.locator("#man-error")).to_contain_text("nur bei Gate READY")
            page.locator("#man-stage").select_option("Draft")
            page.locator("#man-preview").click()
            expect(page.locator("#man-frame")).to_be_visible()
            expect(page.frame_locator("#man-frame").locator(".subtitle")).to_have_text("Kapitel 01 – Grundlagen und Überblick")
            expect(page.frame_locator("#man-frame").locator("body")).to_contain_text("Der Dealer darf Aufträge stornieren.")
            page.locator("#man-generate").click()
            expect(page.locator("#man-ok")).to_contain_text("Handbuchstand Draft für CH01")
            assert list((onedrive / "05_Manual_Generated" / "Draft").glob("CH01_*_Handbuch_Draft.html"))
            expect(page.locator("#clean-rules li")).to_have_count(4)
            expect(page.locator("#clean-empty")).to_be_visible()  # everything is recent
            expect(page.locator("#clean-run")).to_be_disabled()

            # --- dashboard refresh after export
            page.locator('#tabs button[data-tab="dashboard"]').click()
            expect(page.locator('[data-kpi="packages"] .value')).to_have_text("1")
            # newest first – the manual version may share the second with the export, so check the whole list
            expect(page.locator("#dash-outputs tbody")).to_contain_text("06_Exports/Packages/")
            expect(page.locator("#dash-outputs tbody")).to_contain_text("05_Manual_Generated/Draft/")
            expect(page.locator("#dash-imports tbody tr")).to_have_count(5)  # 4 successful + 1 failed import
            failed_row = page.locator("#dash-imports tbody tr", has_text="CH01_ohne_fragen.html")
            expect(failed_row).to_contain_text("FAILED")
            expect(failed_row.locator("td.gate-cell")).to_have_text("BLOCKED")
            expect(page.locator("#dash-imports tbody tr", has_text="CH03_Market")).to_contain_text("Finance Management")
            page.locator("#dash-group").select_option("role")
            expect(page.locator("#dash-imports tbody tr.group-row")).to_have_text(["Alle Rollen (1)", "Dealer (2)", "HQ (1)", "MO (Market Operations) (1)"])
            page.locator("#dash-group").select_option("")
            page.get_by_role("button", name="Aktualisieren").click()
            expect(page.locator("#toast")).to_contain_text("Dashboard aktualisiert")
            shot("01-dashboard")

            # --- design studio
            page.locator('#tabs button[data-tab="design"]').click()
            expect(page.locator("#ds-templates li")).to_have_count(4)
            expect(page.locator('#ds-templates button[data-template="handbuch"]')).to_have_class(re.compile("active"))
            frame = page.frame_locator("#ds-frame")
            expect(frame.locator(".title")).to_have_text("oneSCM Benutzerhandbuch")
            expect(frame.locator("h1").first).to_have_css("font-size", "26.6667px")  # 20 pt
            page.locator('input[aria-label="Überschrift 1 Größe"]').fill("24")
            page.locator("#ds-form details", has_text="Farbpalette").locator("summary").click()
            page.locator("#ds-form details", has_text="Icon-Farbe").locator("summary").click()
            page.locator('input[aria-label="Primär (Titel, H1, Tabellenkopf)"]').fill("#123456")
            expect(page.locator("#ds-preview-state")).to_have_text("Vorschau mit ungespeicherten Änderungen")
            expect(frame.locator("h1").first).to_have_css("font-size", "32px")  # 24 pt, unsaved preview
            expect(frame.locator(".title")).to_have_css("color", "rgb(18, 52, 86)")
            page.locator("#ds-save").click()
            expect(page.locator("#ds-saved")).to_contain_text("gespeichert")
            page.once("dialog", lambda d: d.accept("Handbuch Marke B"))
            page.locator("#ds-new").click()
            expect(page.locator("#ds-templates li")).to_have_count(5)
            expect(page.locator('#ds-templates button[data-template="handbuch-marke-b"]')).to_have_class(re.compile("active"))
            expect(page.locator("#ds-reset")).to_be_disabled()  # own template: nothing to reset to
            page.locator('input[aria-label="Akzent (H2, Linien, Icons)"]').fill("grün")
            expect(page.locator("#ds-error")).to_contain_text("HEX")
            page.locator("#ds-cancel").click()
            expect(page.locator('input[aria-label="Akzent (H2, Linien, Icons)"]')).to_have_value("#00708A")
            page.locator("#ds-form summary", has_text="Layoutboxen").click()
            tip_row = page.locator('#ds-boxes tr[data-box="tip"]')
            tip_row.locator('select[aria-label="Icon Tipp"]').select_option("doc-lightbulb")
            expect(frame.locator(".box.bx-tip use").first).to_have_attribute("href", "#i-doc-lightbulb")
            tip_row.locator('input[aria-label="Tipp Rahmen"]').fill("#123456")
            expect(frame.locator(".box.bx-tip").first).to_have_css("border-left-color", "rgb(18, 52, 86)")
            page.once("dialog", lambda d: d.accept())
            page.locator("#ds-delete").click()
            expect(page.locator("#ds-templates li")).to_have_count(4)
            page.locator('#ds-templates button[data-template="handbuch"]').click()
            expect(page.locator('input[aria-label="Überschrift 1 Größe"]')).to_have_value("24")
            page.once("dialog", lambda d: d.accept())
            page.locator("#ds-reset").click()
            expect(page.locator('input[aria-label="Überschrift 1 Größe"]')).to_have_value("20")
            expect(page.locator("#ds-gallery .gallery a")).to_have_count(91)  # 33 + 40 + 6 icons, 12 flags
            page.locator("#ds-icon-set").select_option("document")
            expect(page.locator("#ds-gallery .gallery a")).to_have_count(40)
            page.locator("#ds-icon-set").select_option("roles")
            expect(page.locator("#ds-gallery .gallery a")).to_have_count(6)
            page.locator("#ds-icon-set").select_option("flags")
            expect(page.locator("#ds-gallery a[data-flag] img")).to_have_count(12)
            page.locator("#ds-icon-set").select_option("")
            expect(frame.locator("img.flag")).to_have_count(12)
            expect(frame.locator(".rb")).not_to_have_count(0)
            page.locator("#ds-form summary", has_text="Schnellvorlagen").click()
            page.locator("#ds-schemes button", has_text="Hoher Kontrast").click()
            expect(frame.locator(".title")).to_have_css("color", "rgb(0, 0, 0)")
            page.locator("#ds-scale-base").fill("11")
            page.locator("#ds-scale-ratio").select_option("1.25")
            page.locator("#ds-scale-apply").click()
            expect(page.locator('input[aria-label="Überschrift 1 Größe"]')).to_have_value("21.5")
            page.locator("#ds-cancel").click()
            expect(page.locator('input[aria-label="Überschrift 1 Größe"]')).to_have_value("20")
            page.locator("#ds-icon-color").select_option(label="Tipp / Belegt #1E7F4F")
            with page.expect_download() as icon_download:
                page.locator('#ds-gallery a[data-icon="verified"]').click()
            assert icon_download.value.suggested_filename == "onescm_verified.svg"
            assert 'stroke="#1E7F4F"' in Path(icon_download.value.path()).read_text(encoding="utf-8")
            with page.expect_download() as word_download:
                page.locator("#ds-dl-dotx").click()
            assert word_download.value.suggested_filename == "handbuch_Formatvorlage.dotx"
            page.locator('#ds-templates button[data-template="quickreference"]').click()
            expect(frame.locator(".cols")).to_have_css("column-count", "2")
            shot("09-designstudio")
            page.locator('#tabs button[data-tab="sync"]').click()
            page.locator("#man-design").select_option("training")
            page.locator("#man-chapter").select_option("CH01")
            page.locator("#man-stage").select_option("Draft")
            page.locator("#man-preview").click()
            expect(page.frame_locator("#man-frame").locator(".hf.top")).to_contain_text("oneSCM Training · Modul 01")
            with page.expect_download() as manual_docx:
                page.locator("#man-docx").click()
            assert manual_docx.value.suggested_filename == "CH01_Handbuch_Draft.docx"
            assert Path(manual_docx.value.path()).read_bytes()[:2] == b"PK"
            page.locator("#man-stage").select_option("Released")
            page.locator("#man-docx").click()
            expect(page.locator("#man-error")).to_contain_text("Gate READY")
            page.locator("#man-stage").select_option("Draft")

            # --- internal chat bot: router → policy → tool
            page.locator('#tabs button[data-tab="chat"]').click()
            page.locator("#chat-registry-box summary").click()
            expect(page.locator("#chat-registry tbody tr")).to_have_count(10)
            expect(page.locator('#chat-registry tr[data-tool="export_knowledge"]')).to_contain_text("WRITE_LOCAL")
            expect(page.locator('#chat-registry tr[data-tool="search_jira"]')).to_contain_text("Connector fehlt")
            expect(page.locator("#chat-policy")).to_contain_text("INTERNAL_RESTRICTED")
            expect(page.locator("#chat-network-guard")).to_have_text("aktiv (nur localhost)")
            page.locator("#chat-examples button", has_text="Validiere Kapitel 1").click()
            last = lambda: page.locator("#chat-log .msg.bot").last
            expect(last().locator(".call").first).to_have_text('validate_chapter({"chapter":"CH01"})')
            expect(last()).to_contain_text("Validierung CH01")
            page.locator("#chat-input").fill("Wofür steht PI?")
            page.locator("#chat-input").press("Enter")
            expect(last()).to_contain_text("PI = Program Increment")
            last().get_by_role("button", name="✓ Ja").click()
            expect(last()).to_contain_text("Als Trainingsbeispiel gespeichert")
            page.locator("#chat-input").fill("Was gilt bei Service Contract Cancellation für Quantencomputer?")
            page.locator("#chat-send").click()
            expect(last()).to_contain_text("Keine freigegebene Quelle gefunden.")
            expect(last().locator(".steps li")).to_have_count(7)
            page.locator("#chat-input").fill("Suche im Internet nach dem Aktienkurs von Mercedes")
            page.locator("#chat-send").click()
            expect(last()).to_have_class(re.compile("denied"))
            expect(last()).to_contain_text("default DENY")
            expect(page.locator("#chat-audit li").first).to_contain_text("DENIED")
            page.locator("#chat-input").fill("Was darf der Dealer bei Aufträgen?")
            page.locator("#chat-send").click()
            hit = last().locator(".result-list li", has_text="Der Dealer darf Aufträge stornieren")
            expect(hit).to_contain_text("Released")
            last().locator("select[aria-label='Richtige Funktion']").select_option("get_claims")
            expect(last()).to_contain_text("Korrektur „get_claims“")
            page.locator("#chat-input").fill("Exportiere CH01 als CSV")
            page.locator("#chat-send").click()
            expect(last()).to_contain_text("Bestätigung erforderlich")
            csv_before = len(list(onedrive.rglob("*_Claims.csv")))
            last().get_by_role("button", name="Export jetzt ausführen").click()
            expect(page.locator("#chat-log .msg.bot", has_text="Export CH01 (csv)")).to_contain_text("Datei(en) lokal im OneDrive-Ordner")
            assert len(list(onedrive.rglob("*_Claims.csv"))) == csv_before + 1
            page.locator("#chat-eval").click()
            expect(page.locator("#chat-eval-score")).to_have_text("Success: 30 / 30")
            page.locator("#chat-mode").select_option("model")
            page.locator("#chat-input").fill("Berechne die Coverage für CH01")
            page.locator("#chat-send").click()
            expect(last().locator(".chat-note")).to_contain_text("Regel-Router")
            page.locator("#chat-mode").select_option("rules")
            with page.expect_download() as training:
                page.locator("#chat-train-notebook").click()
            assert training.value.suggested_filename == "onescm360_router_notebook.jsonl"
            page.locator("#chat-log").evaluate("e => e.scrollTop = 0")
            shot("08-chat")
            page.locator("#chat-log .msg.bot", has_text="Der Dealer darf Aufträge stornieren").locator(".result-list li", has_text="Der Dealer darf Aufträge stornieren").click()
            expect(page.locator('#tabs button[data-tab="claims"]')).to_have_class(re.compile("active"))
            expect(page.locator('#claim-form [data-field="canonicalStatement"]')).to_have_value("Der Dealer darf Aufträge stornieren.")

            # --- documentation
            page.locator('#tabs button[data-tab="docs"]').click()
            expect(page.locator("#docs-body h1").first).to_have_text("oneSCM360 Knowledge Studio")
            expect(page.locator("#docs-body table").first).to_be_visible()

            # --- the selected register survives a reload
            page.reload()
            expect(page.locator('#tabs button[data-tab="docs"]')).to_have_class(re.compile("active"))

            # --- narrow viewport: navigation stays visible
            page.set_viewport_size({"width": 390, "height": 840})
            page.locator('#tabs button[data-tab="import"]').click()
            expect(page.locator("#tabs").get_by_role("button", name="Dokumentation")).to_be_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), "horizontal scroll on mobile"
            shot("07-mobile")
            browser.close()
    finally:
        server.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
    assert not errors, errors
    print("Browser-Workflow erfolgreich.")


if __name__ == "__main__":
    main()
