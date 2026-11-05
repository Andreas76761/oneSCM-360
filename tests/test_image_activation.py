import unittest
import media
class ActivationTests(unittest.TestCase):
 def test_disabled_release_and_domain_filters_skip_output(self):
  item={'id':'assignment','title':'Image','kind':'Bild','frames':[{'variants':[{'asset_id':'image','revision':1}],'caption':''}],'conditions':{}}
  c={'id':'chapter','title':'Chapter','mappings':[{'target_id':'d1','active':True}],'media':[item]}
  for rule in [{'enabled':False},{'enabled':True,'releases':['2.0']},{'enabled':True,'domains':['d3']}]:
   item['activation']=rule
   self.assertEqual(media.compose_chapter(c,{'release':'1.0'}),([],[],[]))
  item['activation']={'enabled':True,'releases':['1.0'],'domains':['d1']}
  self.assertTrue(media.compose_chapter(c,{'release':'1.0'})[1])
  self.assertEqual(media.validate_assignments([item])[0]['activation']['domains'],['d1'])

class PersistenceTests(unittest.TestCase):
 def test_rule_persists_in_outline_and_rejects_old_revision(self):
  import app, tempfile, io, image_activation
  from pathlib import Path
  from PIL import Image
  with tempfile.TemporaryDirectory() as folder:
   store=app.Store(Path(folder)/'db.sqlite3');raw=io.BytesIO();Image.new('RGB',(20,20),'white').save(raw,format='PNG')
   asset=store.media.upload(raw.getvalue(),'Screen','de',{})
   o=app.new_outline('Manual');c=app.chapter('Kapitel');o['chapters']=[c]
   c['media']=[{'id':app.uid(),'title':'Bild','kind':'Bild','frames':[{'variants':[{'asset_id':asset['id'],'revision':1}],'caption':''}],'conditions':{}}]
   o=store.save(o);row=image_activation.listing(store)[0];data={**row,'activation':{'enabled':False,'releases':['1.2'],'domains':['d1']}}
   saved=image_activation.save(store,data)
   self.assertFalse(saved['chapters'][0]['media'][0]['activation']['enabled'])
   self.assertFalse(app.Store(Path(folder)/'db.sqlite3').get(o['id'])['chapters'][0]['media'][0]['activation']['enabled'])
   with self.assertRaises(app.Conflict):image_activation.save(store,data)
