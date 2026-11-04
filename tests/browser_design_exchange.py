"""Real-browser checks for design persistence, chat handoff and batch imports."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright, expect


def main():
    with tempfile.TemporaryDirectory() as directory:
        store=app.Store(Path(directory)/'test.sqlite3')
        outline=app.new_outline('Designprüfung')
        outline['chapters']=[app.chapter('Vertrag',mandatory=True)]
        outline['chapters'][0]['blocks']=[dict(app.block(),text='Hinweis: Vertrag prüfen.',status='Freigegeben')]
        outline=store.save(outline)
        source=store.sources.upload('Beispiel.txt',b'Vertrag oeffnen. LOGIN: demo123',{})
        server=app.make_server(store,0)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True,executable_path=os.environ.get('ONESCM_BROWSER_PATH'))
                page=browser.new_page(viewport={'width':1600,'height':1100})
                errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{server.server_port}')
                page.locator(f'#outline-list [data-id="{outline["id"]}"]').click()
                page.locator('#design-button').click()
                expect(page.locator('#design-dialog')).to_be_visible()
                page.locator('[data-design="chapter"]').fill('#991122')
                page.locator('[data-design="keywords"]').fill('Vertrag')
                page.locator('[data-design="icon_style"]').select_option('letters')
                page.locator('#design-form button[type="submit"]').click()
                page.locator('#save').click()
                page.reload()
                page.locator(f'#outline-list [data-id="{outline["id"]}"]').click()
                page.locator('#design-button').click()
                expect(page.locator('[data-design="chapter"]')).to_have_value('#991122')
                expect(page.locator('[data-design="icon_style"]')).to_have_value('letters')
                page.locator('#design-cancel').click()
                page.locator('#ai-exchange-button').click()
                page.locator('#ai-source').select_option(source['id'])
                chunk=store.sources.chunks(source['id'])[0]
                page.locator('#ai-chunks').select_option(chunk['id'])
                page.locator('#ai-prepare').click()
                expect(page.locator('#ai-state')).to_contain_text('Bereit')
                prompt=page.locator('#ai-prompt').input_value()
                assert 'demo123' not in prompt
                job=store.ai_exchange.listing()[0]
                response=json.dumps({'job_id':job['id'],'title':'Vertrag öffnen','text':'Vertrag öffnen und prüfen.','source_ids':[chunk['id']],'warnings':[]})
                page.locator('#ai-response').fill(response)
                page.locator('#ai-preview').click()
                expect(page.locator('#ai-result')).to_contain_text('Vertrag öffnen und prüfen.')
                page.locator('#ai-reviewed').check();page.locator('#ai-accept').click()
                expect(page.locator('#message')).to_contain_text('Bibliotheksentwurf')
                assert store.library.listing()[0]['block']['status']=='Entwurf'
                page.locator('#ai-close').click();page.locator('#sources-button').click()
                page.locator('#source-files').set_input_files([
                    {'name':'Eins.txt','mimeType':'text/plain','buffer':b'Erster Massentext'},
                    {'name':'Zwei.html','mimeType':'text/html','buffer':b'<html><body><h1>SYN-21: Beispiel</h1><p>Vertrag pruefen.</p></body></html>'}])
                page.locator('#source-upload button[type="submit"]').click()
                expect(page.locator('#source-batch-list')).to_contain_text('1 Chunks importiert')
                expect(page.locator('#source-batch-list li')).to_have_count(2)
                expect(page.locator('#source-batch-list li').nth(1)).to_contain_text('importiert')
                assert len(store.sources.listing())==3
                assert not errors, errors
                browser.close()
        finally:
            server.shutdown();server.server_close()
    print('Browser PASS: design save/reload, chat prompt and reviewed draft, multiple file import, no JavaScript errors.')

if __name__=='__main__':main()
