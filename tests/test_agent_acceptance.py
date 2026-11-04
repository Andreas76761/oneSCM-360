import io
from pathlib import Path
import tempfile
import unittest
from PIL import Image
import app

class ProposalTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=app.Store(Path(self.tmp.name)/'db.sqlite3')
  self.source=self.store.sources.upload('Contract.md',b'# Contract\nDealer contract instructions.',{})
  o=app.new_outline('Contract');o['chapters']=[app.chapter('Contract')];o['chapters'][0]['blocks']=[dict(app.block(),text='Contract instructions.',status='Freigegeben',scope='Standard')];self.o=self.store.save(o)
 def tearDown(self):self.tmp.cleanup()
 def job(self,agents):
  j=self.store.agent_hub.start({'agents':agents,'sources':[self.source['id']],'outline_id':self.o['id']})
  while j['status']=='queued':j=self.store.agent_hub.step({'id':j['id'],'revision':j['revision']})
  return j
 def accept(self,j,stage,**kw):return self.store.agent_hub.accept_proposal({'id':j['id'],'revision':j['revision'],'agent':stage,'index':0,'reviewed':True,**kw})
 def test_knowledge_review_edit_duplicate_and_stale(self):
  j=self.job(['knowledge'])
  with self.assertRaises(app.Invalid):self.accept(j,'knowledge',reviewed=False)
  j=self.accept(j,'knowledge',title='Edited',text='Reviewed text')
  item=self.store.library.listing()[0];self.assertEqual(item['block']['scope'],'Standard');self.assertEqual(item['title'],'Edited');self.assertEqual(item['block']['status'],'Entwurf');self.assertIn(j['id'],item['block']['source'])
  with self.assertRaises(app.Invalid):self.accept(j,'knowledge')
  j=self.job(['knowledge']);self.o['title']='Changed';self.store.save(self.o)
  with self.assertRaises(app.Conflict):self.accept(j,'knowledge')
  self.assertEqual(len(self.store.library.listing()),1)
 def test_classification_is_atomic_and_preserves_other_links(self):
  j=self.job(['classification','knowledge']);c=j['chunks'][0]
  with self.assertRaises(ValueError):self.accept(j,'classification',chapter_ids=['missing'])
  self.assertEqual(self.store.sources.chunks(self.source['id'])[0]['revision'],c['revision'])
  j=self.accept(j,'classification',chapter_ids=[self.o['chapters'][0]['id']])
  saved=self.store.sources.chunks(self.source['id'])[0];self.assertIn('Retailer',saved['labels']['roles']);self.assertEqual(len(saved['assignments']),1)
  self.assertFalse(self.store.agent_hub.get(j['id'])['stale'])
  j=self.accept(j,'knowledge');self.assertEqual(len(j['accepted']),2)
 def test_media_requires_approved_current_revision_and_updates_outline(self):
  raw=io.BytesIO();Image.new('RGB',(30,20),'white').save(raw,format='PNG')
  asset=self.store.media.upload(raw.getvalue(),'Contract','de',{'role':'Retailer'})
  j=self.job(['media'])
  with self.assertRaises(app.Invalid):self.accept(j,'media',chapter_id=self.o['chapters'][0]['id'])
  asset.update(status='Freigegeben',pii_reviewed=True);asset=self.store.media.save(asset)
  with self.assertRaises(app.Invalid):self.accept(j,'media',chapter_id=self.o['chapters'][0]['id'])
  j=self.job(['media']);j=self.accept(j,'media',chapter_id=self.o['chapters'][0]['id'],caption='Reviewed caption')
  saved=self.store.get(self.o['id']);self.assertEqual(saved['chapters'][0]['media'][0]['frames'][0]['caption'],'Reviewed caption')
  self.assertFalse(self.store.agent_hub.get(j['id'])['stale'])
  with self.assertRaises(app.Invalid):self.accept(j,'media',chapter_id=self.o['chapters'][0]['id'])

if __name__=='__main__':unittest.main()
