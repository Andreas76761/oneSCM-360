import os
import sys
import tempfile
import threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright,expect
with tempfile.TemporaryDirectory() as folder:
 store=app.Store(Path(folder)/'db.sqlite3');server=app.make_server(store,0)
 threading.Thread(target=server.serve_forever,daemon=True).start()
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(headless=True,executable_path=os.environ.get('ONESCM_BROWSER_PATH'))
   page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto(f'http://127.0.0.1:{server.server_port}');page.wait_for_function("typeof meta !== 'undefined' && !!meta.token")
   page.locator('#dashboard-button').click();expect(page.locator('#dashboard-content')).to_contain_text('Noch keine Quellen')
   store.sources.upload('Neu.md',b'# New\nContent',{})
   page.locator('#dashboard-refresh').click();expect(page.locator('#dashboard-content')).to_contain_text('MD: 1')
   expect(page.locator('#dashboard-content progress')).to_be_visible();page.locator('#dashboard-close').click()
   assert not errors,errors
   browser.close()
 finally:server.shutdown();server.server_close()
print('PASS: Dashboard empty state, refreshed document counts, storage display and close.')
