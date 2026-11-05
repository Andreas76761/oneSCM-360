import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
import app
import agent_hub
import layouts


def xml(raw):
 with zipfile.ZipFile(io.BytesIO(raw)) as z:return '\n'.join(z.read(n).decode() for n in z.namelist() if n.endswith('.xml'))

class DesignAgentTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.store=app.Store(Path(self.temp.name)/'db.sqlite3')
  self.source=self.store.sources.upload('Design.md',b'# Contract\n\nHinweis: Vertrag pruefen.\n\n## Details\n\nAchtung: Freigabe pruefen.\n\nTipp: Reihenfolge beachten.',{})
 def tearDown(self):self.temp.cleanup()
 def test_standalone_design_preserves_source_and_has_before_after(self):
  t={'chapter_font':'Georgia','chapter_size':26,'chapter_line':1.6,'subchapter_font':'Courier New','subchapter_size':18,'subchapter_line':1.3,'font':'Arial','size':12,'line_height':1.8,'notice_border':False,'attention':'#ffe0cc','attention_border_color':'#aa2233','icon_style':'outline'}
  data={'source_id':self.source['id'],'theme':t}
  result=self.store.source_design.preview(data)
  before=self.store.source_design.preview_file(result['before'].split('/')[-1]).decode()
  after=self.store.source_design.preview_file(result['after'].split('/')[-1]).decode()
  self.assertNotEqual(before,after);self.assertIn('26pt',after);self.assertIn('line-height:1.8',after);self.assertIn('callout attention',after);self.assertIn('<svg',after);self.assertIn('border:none',after)
  raw,_=self.store.source_design.export({**data,'format':'docx'});doc=xml(raw)
  self.assertIn('Georgia',doc);self.assertIn('Courier New',doc);self.assertIn('AA2233',doc.upper());self.assertIn('w:pBdr',doc)
  for fmt in ['pptx','pdf','html']:
   raw,_=self.store.source_design.export({**data,'format':fmt});self.assertGreater(len(raw),100)
  self.assertEqual(self.store.all(),[])
  self.assertEqual(len(self.store.sources.listing()),1)
 def test_patterns_revisions_and_invalid_typography(self):
  a=self.store.source_design.save({'name':'Corporate','theme':{'chapter_size':24}})
  b=self.store.source_design.save({**a,'theme':{**a['theme'],'tip_border':False}})
  self.assertEqual(b['revision'],2)
  with self.assertRaises(app.Conflict):self.store.source_design.save(a)
  self.assertEqual(self.store.source_design.listing()[0]['theme']['tip_border'],False)
  for t in [{'chapter_size':100},{'line_height':0},{'chapter_font':'<script>'},{'attention_border':'yes'},{'notice_border_color':'red'}]:
   with self.assertRaises(app.Invalid):layouts.theme(t)
 def setup_outline_library(self):
  o=app.new_outline('Contract Manual');o['chapters']=[app.chapter('Contract')];o['chapters'][0]['blocks']=[dict(app.block(),text='Contract approved instructions.',status='Freigegeben')];o=self.store.save(o)
  entry=self.store.library.save({'id':app.uid(),'revision':0,'title':'Contract text','block':dict(app.block(),text='Vertrag nach Freigabe öffnen.',status='Freigegeben'),'domains':[],'tags':''})
  return o,entry
 def test_eight_agent_stages_and_reviewed_translation_draft(self):
  o,e=self.setup_outline_library()
  job=self.store.agent_hub.start({'outline_id':o['id'],'sources':[self.source['id']],'library_ref':{'id':e['id'],'revision':e['revision']},'agents':[a['id'] for a in agent_hub.CATALOG],'target_language':'en'})
  while job['status']=='queued':job=self.store.agent_hub.step({'id':job['id'],'revision':job['revision']})
  self.assertEqual(job['index'],9);self.assertEqual(job['status'],'review');self.assertEqual(len(job['reports']),9)
  self.assertTrue(job['translation']['prompt']);self.assertEqual(job['translation']['proposal'],'')
  self.assertIn('render_request',job['reports'][-1])
  job=self.store.agent_hub.translation({'id':job['id'],'revision':job['revision'],'text':'Open the contract after approval.'})
  with self.assertRaises(app.Invalid):self.store.agent_hub.accept_translation({'id':job['id'],'revision':job['revision']})
  job=self.store.agent_hub.accept_translation({'id':job['id'],'revision':job['revision'],'reviewed':True})
  result=next(e for e in self.store.library.listing() if e['id']==job['translation']['library_id'])
  self.assertEqual(result['block']['status'],'Entwurf');self.assertEqual(result['block']['language'],'en');self.assertFalse(result['translation']['reviewed'])
  self.assertEqual(self.store.get(o['id'])['revision'],o['revision'])
 def test_stale_inputs_cancel_and_unapproved_translation(self):
  o,e=self.setup_outline_library()
  e['block']['status']='Entwurf';e=self.store.library.save(e)
  with self.assertRaises(app.Invalid):self.store.agent_hub.start({'agents':['translation'],'library_ref':{'id':e['id'],'revision':e['revision']}})
  job=self.store.agent_hub.start({'agents':['extraction'],'sources':[self.source['id']]})
  self.store.sources.delete(self.source['id'])
  with self.assertRaises(app.Conflict):self.store.agent_hub.step({'id':job['id'],'revision':job['revision']})
  cancelled=self.store.agent_hub.cancel({'id':job['id'],'revision':job['revision']})
  self.assertEqual(cancelled['status'],'cancelled')
 def test_source_context_changes_invalidate_classification(self):
  o,e=self.setup_outline_library()
  job=self.store.agent_hub.start({'agents':['classification'],'sources':[self.source['id']],'outline_id':o['id']})
  self.store.review.save_context({'id':self.source['id'],'revision':0,'language':'de','market':'DE'})
  self.assertTrue(self.store.agent_hub.get(job['id'])['stale'])
  with self.assertRaises(app.Conflict):self.store.agent_hub.step({'id':job['id'],'revision':job['revision']})

if __name__=='__main__':unittest.main()
