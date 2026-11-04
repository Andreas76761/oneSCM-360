import io
from pathlib import Path
import tempfile
import unittest
from PIL import Image
import app

class RAGTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.store=app.Store(Path(self.temp.name)/'db.sqlite3')
  o=app.new_outline('Vertrag Manual');o['chapters']=[app.chapter('Vertrag')]
  o['chapters'][0]['blocks']=[dict(app.block(),text='Vertrag darf nicht storniert werden.',status='Freigegeben'),dict(app.block(),text='PRIVATESECRET Vertrag',internal=True,role='HQ',status='Freigegeben')]
  self.o=self.store.save(o)
  self.source=self.store.sources.upload('vertrag.md',b'Vertrag in drei Schritten erstellen.',{})
  self.internal=self.store.internal.save({'id':app.uid(),'revision':0,'title':'Vertrag FAQ','question':'Wie wird der Vertrag getestet?','answer':'Nur in Preprod testen.','body':'PRIVATEBODY','note':'PRIVATENOTE','categories':['internal-it'],'roles':['Retailer'],'markets':['DE'],'status':'Freigegeben','chatbot_enabled':True,'language':'de'})
  self.data={'profile':{**app.profile(),'market':'DE','as_of':'2026-11-04'},'query':'Vertrag'}
 def tearDown(self):self.temp.cleanup()
 def refs(self,row):return [{'ref':row['ref'],'fingerprint':row['fingerprint']}]
 def test_public_retrieval_and_internal_filter(self):
  public=self.store.rag.search(self.data)
  self.assertTrue(any(r['kind']=='source' for r in public['results']))
  self.assertFalse(any(r['internal'] for r in public['results']))
  self.assertNotIn('PRIVATE',str(public))
  internal=self.store.rag.search({**self.data,'include_internal':True,'working_role':'intern'})
  self.assertTrue(any(r['kind']=='faq' for r in internal['results']))
  with self.assertRaises(app.Invalid):self.store.rag.search({**self.data,'include_internal':True,'working_role':'Retailer'})
  hq=self.store.rag.search({**self.data,'profile':{**self.data['profile'],'role':'HQ'}})
  self.assertNotIn('PRIVATESECRET',str(hq))
 def test_answers_are_complete_approved_evidence_and_no_unknown_source_claim(self):
  answer=self.store.rag.answer(self.data)
  self.assertTrue(any('darf nicht' in c['text'] for c in answer['citations']))
  self.assertTrue(all(c['approved'] and c['kind']!='source' for c in answer['citations']))
  self.assertEqual(self.store.rag.answer({**self.data,'query':'unauffindbarxyz'})['citations'],[])
 def test_chapter_insertion_is_draft_scoped_and_rejects_internal_and_stale(self):
  row=next(r for r in self.store.rag.search(self.data)['results'] if r['kind']=='source')
  data={**self.data,'refs':self.refs(row),'outline_id':self.o['id'],'outline_revision':self.o['revision'],'title':'Neues Rollen-Kapitel','parent_id':self.o['chapters'][0]['id'],'reviewed':True}
  saved=self.store.rag.chapter(data);c=saved['chapters'][-1]
  self.assertEqual(c['level'],2);self.assertEqual(c['blocks'][0]['status'],'Entwurf')
  self.assertEqual(c['config']['conditions'],{'role':['Retailer'],'language':['de']})
  with self.assertRaises(app.Conflict):self.store.rag.chapter(data)
  internal_data={**self.data,'include_internal':True,'working_role':'intern'}
  row=next(r for r in self.store.rag.search(internal_data)['results'] if r['kind']=='faq')
  with self.assertRaises(app.Invalid):self.store.rag.chapter({**data,**internal_data,'refs':self.refs(row),'outline_revision':saved['revision']})
  row=next(r for r in self.store.rag.search(self.data)['results'] if r['kind']=='source')
  self.store.sources.delete(self.source['id'])
  with self.assertRaises(app.Conflict):self.store.rag.evidence({**self.data,'refs':self.refs(row)})
 def test_language_and_role_filters_and_approved_screen_insertion(self):
  raw=io.BytesIO();Image.new('RGB',(60,40),'white').save(raw,format='PNG')
  asset=self.store.media.upload(raw.getvalue(),'Vertrag Screen','de',{'role':'Retailer','market':'DE'})
  screen=next(r for r in self.store.rag.search({**self.data,'kind':'screen'})['results'])
  args={**self.data,'refs':self.refs(screen),'outline_id':self.o['id'],'outline_revision':self.o['revision'],'title':'Screenkapitel','reviewed':True}
  with self.assertRaises(app.Invalid):self.store.rag.chapter(args)
  asset.update(status='Freigegeben',pii_reviewed=True);asset=self.store.media.save(asset)
  screen=self.store.rag.search({**self.data,'kind':'screen'})['results'][0]
  saved=self.store.rag.chapter({**args,'refs':self.refs(screen)})
  self.assertEqual(saved['chapters'][-1]['media'][0]['frames'][0]['variants'][0]['revision'],asset['revision'])
  for change in [{'language':'en'},{'role':'HQ'}]:
   self.assertEqual(self.store.rag.search({**self.data,'profile':{**self.data['profile'],**change},'kind':'screen'})['results'],[])
 def test_attach_screens_to_existing_chapter_and_revision_conflict(self):
  raw=io.BytesIO();Image.new('RGB',(30,20),'white').save(raw,format='PNG')
  asset=self.store.media.upload(raw.getvalue(),'Vertrag Zuordnung','de',{'role':'Retailer','market':'DE'})
  asset.update(status='Freigegeben',pii_reviewed=True);asset=self.store.media.save(asset)
  screen=self.store.rag.search({**self.data,'kind':'screen'})['results'][0]
  args={**self.data,'refs':self.refs(screen),'outline_id':self.o['id'],'outline_revision':self.o['revision'],'parent_id':self.o['chapters'][0]['id'],'reviewed':True}
  saved=self.store.rag.attach_screens(args)
  self.assertEqual(len(saved['chapters']),len(self.o['chapters']))
  self.assertEqual(saved['chapters'][0]['media'][0]['frames'][0]['variants'][0]['asset_id'],asset['id'])
  with self.assertRaises(app.Conflict):self.store.rag.attach_screens(args)

 def test_pending_jobs_are_searchable_but_never_reader_sources(self):
  self.store.orchestrator.start({'outline_id':self.o['id'],'sources':[self.source['id']],'agents':['triage'],'mode':'rules'})
  found=self.store.rag.search({**self.data,'kind':'work','include_internal':True,'working_role':'intern'})
  self.assertTrue(any(r['kind']=='task' for r in found['results']))

if __name__=='__main__':unittest.main()
