import tempfile
import unittest
from pathlib import Path
import app
import source_collection

class CollectionTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.store=app.Store(Path(self.temp.name)/'db.sqlite3')
  self.ids=[self.store.sources.upload(name,text.encode(),{})['id'] for name,text in [('a.md','# Titel\nVertrag prüfen.'),('b.html','<h1>Zweiter Titel</h1><p>Frist beachten.</p>')]]
 def tearDown(self):self.temp.cleanup()
 def test_merge_preserves_sources_chunks_and_provenance(self):
  preview=source_collection.collect(self.store,{'ids':self.ids})
  result=source_collection.save(self.store,{'ids':self.ids,'fingerprint':preview['fingerprint'],'name':'Sammlung','text':preview['text']})
  self.assertEqual(len(self.store.sources.listing()),3)
  chunks=self.store.sources.chunks(result['id']);self.assertEqual(len(chunks),2)
  self.assertEqual(chunks[0]['details']['source_ref']['source_id'],self.ids[0])
  self.assertEqual(chunks[0]['assignments'],[])
  self.assertIn('Frist beachten',preview['text'])
 def test_edited_summary_and_stale_sources(self):
  preview=source_collection.collect(self.store,{'ids':self.ids})
  self.assertIn('keine KI',preview['summary'])
  result=source_collection.save(self.store,{'ids':self.ids,'fingerprint':preview['fingerprint'],'name':'Auszug.md','text':preview['summary']})
  self.assertTrue(self.store.sources.chunks(result['id']))
  with self.store.connect() as db:db.execute('UPDATE chunks SET text=? WHERE source_id=?',('Geändert',self.ids[0]))
  with self.assertRaises(app.Conflict):source_collection.save(self.store,{'ids':self.ids,'fingerprint':preview['fingerprint'],'name':'alt','text':preview['text']})
 def test_empty_duplicate_and_deleted_selection_rejected(self):
  for ids in [[],[self.ids[0],self.ids[0]],['missing']]:
   with self.assertRaises(app.Invalid):source_collection.collect(self.store,{'ids':ids})
