import os
import io
from PIL import Image
from pathlib import Path
import sys
import tempfile
import threading
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright,expect

with tempfile.TemporaryDirectory() as folder:
 store=app.Store(Path(folder)/'test.sqlite3')
 o=app.new_outline('RAG Ziel');o['profile']['market']='DE';o=store.save(o)
 raw=io.BytesIO();Image.new('RGB',(80,60),'white').save(raw,format='PNG')
 asset=store.media.upload(raw.getvalue(),'Vertrag Screen','de',{'role':'Retailer','market':'DE'});asset.update(status='Freigegeben',pii_reviewed=True);asset=store.media.save(asset)
 store.sources.upload('Vertrag.md',b'Vertrag anlegen und Laufzeit pruefen.',{})
 store.internal.save({'id':app.uid(),'revision':0,'title':'Vertrag Test FAQ','question':'Wie Vertrag testen?','answer':'Vertrag ausschliesslich in Preprod testen.','categories':['internal-it'],'roles':['Retailer'],'markets':['DE'],'status':'Freigegeben','chatbot_enabled':True})
 server=app.make_server(store,0);threading.Thread(target=server.serve_forever,daemon=True).start()
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(headless=True,executable_path=os.environ.get('ONESCM_BROWSER_PATH'))
   page=browser.new_page(viewport={'width':1600,'height':1100});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto(f'http://127.0.0.1:{server.server_port}');page.locator(f'#outline-list [data-id="{o["id"]}"]').click()
   page.locator('#rag-button').click();page.locator('#rag-query').fill('Vertrag');page.locator('#rag-kind').select_option('source');page.locator('#rag-search').click()
   expect(page.locator('#rag-results')).to_contain_text('Vertrag anlegen')
   page.locator('[data-rag-detail]').click();expect(page.locator('#rag-detail-body')).to_contain_text('Laufzeit');page.locator('#rag-detail-close').click()
   page.locator('[data-rag-select]').check();page.locator('#rag-title').fill('Vertrag erstellen');page.locator('#rag-reviewed').check();page.locator('#rag-create').click()
   expect(page.locator('#rag-dialog')).not_to_be_visible();expect(page.locator('#chapter-title')).to_have_value('Vertrag erstellen')
   saved=store.get(o['id']);assert saved['chapters'][-1]['blocks'][0]['role']=='Retailer'
   page.locator('#rag-button').click();page.locator('#rag-internal').check();page.locator('#rag-kind').select_option('faq');page.locator('#rag-query').fill('Vertrag');page.locator('#rag-search').click()
   expect(page.locator('#rag-results')).to_contain_text('kein Leseroutput');expect(page.locator('[data-rag-select]')).to_be_disabled()
   page.locator('#rag-answer').click();expect(page.locator('#rag-answer-result')).to_contain_text('Preprod')
   page.locator('#rag-open-chat').click();expect(page.locator('#chat-dialog')).to_be_visible();expect(page.locator('#chat-question')).to_have_value('Vertrag')
   page.locator('#chat-rag-search').click();expect(page.locator('#rag-dialog')).to_be_visible();expect(page.locator('#rag-query')).to_have_value('Vertrag')
   page.locator('#rag-kind').select_option('screen');page.locator('#rag-search').click()
   expect(page.locator('#rag-results')).to_contain_text('Vertrag Screen')
   page.locator('[data-rag-detail]').click();expect(page.locator('#rag-detail-body img')).to_be_visible();page.locator('#rag-detail-close').click()
   page.locator('[data-rag-select]').check();page.locator('#rag-parent').select_option(o['chapters'][0]['id']);page.locator('#rag-reviewed').check();page.locator('#rag-attach-screens').click()
   expect(page.locator('#rag-dialog')).not_to_be_visible()
   assert store.get(o['id'])['chapters'][0]['media'][0]['frames'][0]['variants'][0]['asset_id']==asset['id']
   assert not errors,errors
   browser.close()
 finally:server.shutdown();server.server_close()
print('Browser PASS: central retrieval, full evidence, scoped chapter draft, internal exclusion, FAQ evidence and bidirectional chat navigation.')
