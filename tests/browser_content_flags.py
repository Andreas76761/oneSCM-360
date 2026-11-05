import os,sys,tempfile,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright,expect
with tempfile.TemporaryDirectory() as folder:
 store=app.Store(Path(folder)/'db.sqlite3');store.sources.upload('Manual_v1.2_2026-11-05.md',b'The contract is for the customer and the user in this market.',{})
 server=app.make_server(store,0);threading.Thread(target=server.serve_forever,daemon=True).start()
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(headless=True,executable_path=os.environ.get('ONESCM_BROWSER_PATH'));page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto(f'http://127.0.0.1:{server.server_port}');page.wait_for_function("typeof meta !== 'undefined' && !!meta.token")
   page.locator('#content-flags-button').click();page.locator('[data-action=analyse]').click();expect(page.locator('#flags-list')).to_contain_text('EN · 2026-11-05 · 1.2')
   page.locator('[data-field=reviewed]').check();page.locator('[data-action=save]').click();expect(page.locator('#flags-list')).to_contain_text('Bestätigt')
   page.locator('#flags-close').click();page.locator('#image-activation-button').click();expect(page.locator('#image-activation-list')).to_contain_text('Noch keine Bilder');assert not errors,errors
   browser.close()
 finally:server.shutdown();server.server_close()
print('PASS: language flags analysis, persisted confirmation, image rules empty state')
