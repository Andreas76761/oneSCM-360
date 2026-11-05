import tempfile,unittest
from pathlib import Path
import app,storage_view
class StorageTests(unittest.TestCase):
 def test_all_tables_metadata_and_pagination(self):
  with tempfile.TemporaryDirectory() as folder:
   s=app.Store(Path(folder)/'db.sqlite3');s.sources.upload('test.md',b'# Hello\nText',{})
   result=storage_view.inventory(s,{});self.assertIn('sources',result['tables']);self.assertTrue(result['database_path'].endswith('db.sqlite3'))
   result=storage_view.inventory(s,{'table':'sources'});self.assertEqual(result['items'][0]['title'],'test.md');self.assertGreater(result['items'][0]['bytes'],0)
   self.assertEqual(storage_view.inventory(s,{'table':'sources','page':1})['items'],[])
   with self.assertRaises(app.Invalid):storage_view.inventory(s,{'table':'sources; DROP TABLE sources'})
   with self.assertRaises(app.Invalid):storage_view.inventory(s,{'page':-1})
