"""Real browser acceptance of internal chat, reviewed conflicts and release promotion."""
from datetime import date
import os
from pathlib import Path
import sys
import tempfile
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright, expect


def main():
    with tempfile.TemporaryDirectory() as directory:
        store=app.Store(Path(directory)/"test.sqlite3")
        outline=app.new_outline("Preprod acceptance")
        outline["profile"].update(environment="preprod",market="DE",release="2026.11",as_of=date.today().isoformat())
        outline["chapters"]=[app.chapter("Testvertrag",mandatory=True)]
        outline["chapters"][0]["config"]={"status":"Freigegeben"}
        outline["chapters"][0]["blocks"]=[dict(app.block(),text="Der Testvertrag hat eine Laufzeit von 24 Monaten.",status="Freigegeben")]
        outline=store.save(store.save(outline),releasing=True)
        entry=store.internal.save({"id":app.uid(),"revision":0,"title":"Testzugang","question":"Wie wird der Testzugang aktiviert?",
            "answer":"Den Testzugang durch das interne IT-Team aktivieren lassen.","categories":["internal-it"],"roles":["HQ"],"markets":["DE"],
            "source":"Confluence Export · SCM-17 · Seite 3","chatbot_enabled":True,"status":"Freigegeben"})
        ids=[]
        for name,months in [("Altstand.txt",12),("Neuer Stand.txt",24)]:
            source=store.sources.upload(name,f"Der Testvertrag hat eine Laufzeit von {months} Monaten.".encode(),{"release":"2026.10" if months==12 else "2026.11"})
            ids.append(source["id"])
            chunk=store.sources.chunks(source["id"])[0]
            store.sources.review({"id":chunk["id"],"revision":chunk["revision"],"labels":{},"assignments":[{"outline_id":outline["id"],"chapter_id":outline["chapters"][0]["id"]}]},set())
        server=app.make_server(store,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True,executable_path=os.environ.get("ONESCM_BROWSER_PATH"))
                page=browser.new_page(viewport={"width":1650,"height":1100})
                errors=[];page.on("pageerror",lambda error:errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{server.server_port}")
                page.locator("#chat-button").click()
                page.locator('#chat-profile [data-key="market"]').fill("DE")
                page.locator('#chat-profile [data-key="role"]').select_option("HQ")
                page.locator("#chat-question").fill("Wie wird der Testzugang aktiviert?")
                page.locator("#chat-send").click()
                expect(page.locator("#chat-turns")).to_contain_text(entry["answer"])
                page.locator("#chat-turns details summary").click()
                expect(page.locator("#chat-turns")).to_contain_text("SCM-17")
                page.locator("[data-chat-cite]").click()
                expect(page.locator("#internal-history")).to_contain_text("R1")
                expect(page.locator("#internal-history")).to_contain_text(entry["answer"])
                page.locator("#internal-history-close").click()
                entry["answer"]="Das interne IT-Team prüft und aktiviert den Testzugang."
                store.internal.save(entry)
                page.locator("#chat-close").click();page.locator("#chat-button").click()
                expect(page.locator("#chat-turns .stale")).to_contain_text("inzwischen geändert")
                page.locator("#chat-new").click()
                page.locator('#chat-profile [data-key="market"]').fill("FR")
                page.locator("#chat-question").fill("Wie wird der Testzugang aktiviert?")
                page.locator("#chat-send").click()
                expect(page.locator("#chat-turns")).to_contain_text("keine ausreichend passenden")
                page.locator("#chat-close").click()
                # Source comparison with explicit contexts and evidence decisions.
                page.locator("#conflicts-button").click()
                page.locator("#conflict-context-open").click()
                page.locator("#context-source").select_option(ids[0])
                page.locator('#source-context-fields [data-key="market"]').fill("DE")
                page.locator("#context-save").click()
                expect(page.locator("#source-context-dialog")).not_to_be_visible()
                page.locator("#conflict-sources").select_option(ids)
                page.locator("#conflict-scan").click()
                expect(page.locator("#conflict-list .knowledge-card")).to_have_count(1)
                expect(page.locator("#conflict-list")).to_contain_text("12 Monaten")
                expect(page.locator("#conflict-list")).to_contain_text("24 Monaten")
                expect(page.locator("#conflict-list")).to_contain_text("Preprod acceptance")
                page.locator("#conflicts-close").click()
                # Preview is blocked while the source difference remains unresolved.
                page.locator("#releases-button").click()
                page.locator("#release-version").fill("2026.11")
                page.locator("#release-sources").select_option(outline["id"])
                page.locator("#release-prepare").click()
                expect(page.locator("#release-detail")).to_contain_text("Quellenprüfung offen")
                expect(page.locator("#release-execute")).to_be_disabled()
                page.locator("#releases-close").click()
                page.locator("#conflicts-button").click()
                page.locator("[data-decision-status]").select_option("Geklärt")
                page.locator("[data-preferred]").select_option("right")
                page.locator("[data-decision-note]").fill("Im neuen Release gilt 24 Monate; Manuskript geprüft und abgeglichen.")
                page.locator("[data-decide]").click()
                expect(page.locator("#conflict-list h3")).to_contain_text("Geklärt")
                page.locator("[data-review-history]").click()
                expect(page.locator("#knowledge-history")).to_contain_text("R2")
                page.locator("#knowledge-history-close").click()
                page.locator("#conflicts-close").click()
                # Refresh the exact package, review, activate, then roll back.
                page.locator("#releases-button").click()
                page.locator("#release-refresh").click()
                expect(page.locator("#release-detail")).to_contain_text("ohne Blocker")
                page.locator("#release-note").fill("Änderungen und DE-Profil fachlich geprüft.")
                page.locator("#release-ack").check()
                page.locator("#release-execute").click()
                expect(page.locator("#release-active")).to_contain_text("Aktiver Prod-Stand: 2026.11")
                expect(page.locator("#release-detail h3")).to_contain_text("Aktiviert")
                if os.environ.get("ONESCM_SCREENSHOT_DIR"):
                    Path(os.environ["ONESCM_SCREENSHOT_DIR"]).mkdir(parents=True,exist_ok=True)
                    page.screenshot(path=str(Path(os.environ["ONESCM_SCREENSHOT_DIR"])/"release-promotion.png"))
                page.locator("#release-note").fill("Test der kontrollierten Rücknahme.")
                page.locator("#release-ack").check()
                page.locator("#release-execute").click()
                expect(page.locator("#release-active")).to_contain_text("Noch keine aktive")
                expect(page.locator("#release-detail h3")).to_contain_text("Zurückgenommen")
                expect(page.locator("#release-events")).to_contain_text("Nach Prod übernommen")
                expect(page.locator("#release-events")).to_contain_text("Zurückgenommen")
                assert store.get(outline["id"])["profile"]["environment"]=="preprod"
                assert not errors,errors
                browser.close()
                print("Browser PASS: cited internal chat, historical evidence, stale notices, profile isolation, source contexts, conflict decisions, blocked preview, reviewed atomic promotion and rollback.")
        finally:
            server.shutdown();server.server_close();thread.join()


if __name__=="__main__":main()
