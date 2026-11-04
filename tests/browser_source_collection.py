import os
from pathlib import Path
import sys
import tempfile
import threading
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright,expect

with tempfile.TemporaryDirectory() as folder:
 store=app.Store(Path(folder)/'db.sqlite3')
 outline=app.new_outline('Ziel');store.save(outline)
 for name,text in [('eins.md','Vertrag eins'),('zwei.md','Vertrag zwei'),('drei.html','<p>Vertrag drei</p>')]:store.sources.upload(name,text.encode(),{})
 server=app.make_server(store,0);threading.Thread(target=server.serve_forever,daemon=True).start()
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(headless=True,executable_path=os.environ.get('ONESCM_BROWSER_PATH'))
   page=browser.new_page(viewport={'width':1500,'height':1100});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto(f'http://127.0.0.1:{server.server_port}');page.locator('#sources-button').click()
   page.locator('#source-type').select_option('md');expect(page.locator('#source-list .source-card')).to_have_count(2)
   page.locator('#sources-select-all').click();expect(page.locator('#sources-selection')).to_contain_text('2 Dateien markiert')
   page.locator('#source-type').select_option('html');expect(page.locator('#sources-selection')).to_contain_text('2 markierte außerhalb')
   page.locator('#sources-select-all').click();expect(page.locator('#sources-selection')).to_contain_text('3 Dateien markiert')
   page.locator('#sources-select-none').click();expect(page.locator('#sources-selection')).to_contain_text('0 Dateien markiert')
   page.locator('#source-type').select_option('md');page.locator('#sources-select-all').click()
   page.locator('#sources-process').click();expect(page.locator('#message')).to_contain_text('2/2:')
   page.locator('#sources-merge').click();expect(page.locator('#collection-info')).to_contain_text('2 Dateien')
   assert 'Vertrag eins' in page.locator('#collection-text').input_value()
   page.locator('#collection-summary').click();assert 'keine KI' in page.locator('#collection-text').input_value()
   page.locator('#collection-text').fill('Redaktionell zusammengestellter Text.')
   with page.expect_download() as event:page.locator('#collection-download').click()
   assert 'Redaktionell' in Path(event.value.path()).read_text()
   page.locator('#collection-name').fill('Neu.md');page.locator('#collection-save').click()
   expect(page.locator('#source-collection-dialog')).not_to_be_visible()
   expect(page.locator('#source-chunks-title')).to_contain_text('Neu.md')
   assert len(store.sources.listing())==4
   assert not errors,errors
   browser.close()
 finally:server.shutdown();server.server_close()
print('Browser PASS: file filters, visible/all selection, batch triage, editable excerpts, Markdown download and derived source.')
