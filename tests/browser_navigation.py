import os,sys,tempfile,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright,expect
with tempfile.TemporaryDirectory() as folder:
 store=app.Store(Path(folder)/'db.sqlite3');server=app.make_server(store,0);threading.Thread(target=server.serve_forever,daemon=True).start()
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(headless=True,executable_path=os.environ.get('ONESCM_BROWSER_PATH'));page=browser.new_page(viewport={'width':1400,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto(f'http://127.0.0.1:{server.server_port}');expect(page.locator('#sources-button')).to_have_text('Quellen & Chunks (0)');expect(page.locator('#appendices-button .navigation-new')).to_have_text('Neu')
   page.locator('#navigation-toggle').click();expect(page.locator('#main-navigation')).to_be_hidden();expect(page.locator('#navigation-toggle')).to_have_attribute('aria-expanded','false')
   page.reload();expect(page.locator('#main-navigation')).to_be_hidden();page.locator('#navigation-toggle').click();expect(page.locator('#main-navigation')).to_be_visible()
   store.sources.upload('a.md',b'# Test\nText',{});page.evaluate("window.dispatchEvent(new Event('onescm-data-change'))");expect(page.locator('#sources-button')).to_have_text('Quellen & Chunks (1)')
   page.locator('#sources-button').focus();page.keyboard.press('Escape');expect(page.locator('#navigation-toggle')).to_be_focused();expect(page.locator('#main-navigation')).to_be_hidden()
   mobile=browser.new_page(viewport={'width':390,'height':844});mobile.goto(f'http://127.0.0.1:{server.server_port}');expect(mobile.locator('#main-navigation')).to_be_hidden();mobile.locator('#navigation-toggle').click();expect(mobile.locator('#main-navigation')).to_be_visible();assert not errors,errors
   browser.close()
 finally:server.shutdown();server.server_close()
print('PASS: navigation toggle, persistence, counts, new badges, keyboard and mobile')
