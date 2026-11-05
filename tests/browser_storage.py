import os,sys,tempfile,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright,expect
with tempfile.TemporaryDirectory() as folder:
 store=app.Store(Path(folder)/'db.sqlite3');store.sources.upload('Stored.md',b'# Stored\nContent',{});server=app.make_server(store,0);threading.Thread(target=server.serve_forever,daemon=True).start()
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(headless=True,executable_path=os.environ.get('ONESCM_BROWSER_PATH'));page=browser.new_page(viewport={'width':1600,'height':1100});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto(f'http://127.0.0.1:{server.server_port}');page.wait_for_function("typeof meta !== 'undefined' && !!meta.token")
   page.locator('#storage-button').click();expect(page.locator('#storage-location')).to_contain_text('db.sqlite3');page.locator('#storage-table').select_option('sources');expect(page.locator('#storage-rows')).to_contain_text('Stored.md')
   handle=page.locator('#storage-dialog .dialog-drag-handle');before=page.locator('#storage-dialog').bounding_box();handle.focus();page.keyboard.press('ArrowDown');after=page.locator('#storage-dialog').bounding_box();assert after['y']>before['y']
   box=handle.bounding_box();page.mouse.move(box['x']+40,box['y']+15);page.mouse.down();page.mouse.move(box['x']+40,box['y']+55);page.mouse.up();assert page.locator('#storage-dialog').bounding_box()['y']>after['y']
   page.locator('#storage-dialog').get_by_role('button',name='Fenster schließen',exact=True).click();expect(page.locator('#storage-dialog')).not_to_be_visible();assert not errors,errors
   browser.close()
 finally:server.shutdown();server.server_close()
print('PASS: storage location, item metadata, dialog keyboard movement, dragging and close')
