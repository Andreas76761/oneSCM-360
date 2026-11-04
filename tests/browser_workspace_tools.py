"""End-to-end backup review/restore and profile batch downloads."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright,expect


def main():
    with tempfile.TemporaryDirectory() as folder:
        store=app.Store(Path(folder)/'workspace.sqlite3')
        outline=app.new_outline('Sicherungsstand')
        outline['chapters']=[app.chapter('Vertrag',mandatory=True)]
        outline['chapters'][0]['blocks']=[dict(app.block(),text='Vertrag '+lang,language=lang,status='Freigegeben') for lang in ['de','en','fr']]
        outline=store.save(outline)
        server=app.make_server(store,0);threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True,executable_path=os.environ.get('ONESCM_BROWSER_PATH'))
                page=browser.new_page(viewport={'width':1600,'height':1100});errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)));page.on('dialog',lambda d:d.accept())
                base=f'http://127.0.0.1:{server.server_port}';page.goto(base)
                page.locator(f'#outline-list [data-id="{outline["id"]}"]').click()
                page.locator('#variants-button').click();page.locator('#variants-preview').click()
                expect(page.locator('#variants-results h3')).to_have_text('18 Dateien')
                page.locator('#variants-reviewed').check()
                with page.expect_download() as event:page.locator('#variants-export').click()
                raw=Path(event.value.path()).read_bytes()
                with zipfile.ZipFile(io.BytesIO(raw)) as z:assert len(json.loads(z.read('Pruefbericht.json'))['files'])==18
                page.locator('#variants-close').click();page.locator('#backup-button').click()
                with page.expect_download() as event:page.locator('#backup-download').click()
                backup=Path(event.value.path()).read_bytes()
                changed=store.get(outline['id']);changed['title']='Nach Sicherung geändert';store.save(changed)
                page.locator('#backup-file').set_input_files({'name':'Sicherung.zip','mimeType':'application/zip','buffer':backup})
                page.locator('#backup-inspect').click();expect(page.locator('#backup-preview')).to_contain_text('Geprüfte Sicherung')
                page.locator('#backup-restore').click();expect(page.locator('.dialog-error')).to_contain_text('WIEDERHERSTELLEN')
                assert store.get(outline['id'])['title']=='Nach Sicherung geändert'
                old_token=page.evaluate('meta.token')
                page.locator('#backup-confirm').fill('WIEDERHERSTELLEN')
                with page.expect_navigation(wait_until='load'):
                    page.locator('#backup-restore').click()
                expect(page.locator('#outline-list')).to_contain_text('Sicherungsstand')
                assert store.get(outline['id'])['title']=='Sicherungsstand'
                response=page.request.post(base+'/api/create',headers={'X-Local-Token':old_token},data={'title':'stale'})
                assert response.status==403
                assert list((Path(folder)/'backups').glob('*.zip'))
                assert not errors,errors
                browser.close()
        finally:server.shutdown();server.server_close()
    print('Browser PASS: 18 document variants, backup download/review, explicit restore, recovery file and old-session rejection.')

if __name__=='__main__':main()
