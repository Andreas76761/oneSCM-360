import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import app
import dashboard

class DashboardTests(unittest.TestCase):
 def test_counts_storage_and_deletion(self):
  with tempfile.TemporaryDirectory() as folder:
   store=app.Store(Path(folder)/'db.sqlite3')
   self.assertEqual(dashboard.snapshot(store)['counts']['documents'],0)
   source=store.sources.upload('test.md',b'# Test\nContent',{})
   raw=io.BytesIO();Image.new('RGB',(30,20),'white').save(raw,format='PNG')
   image=store.media.upload(raw.getvalue(),'Test','de',{})
   image.update(status='Freigegeben',pii_reviewed=True);store.media.save(image)
   result=dashboard.snapshot(store)
   self.assertEqual(result['counts']['documents'],1);self.assertEqual(result['counts']['images'],1);self.assertEqual(result['counts']['approved_images'],1)
   self.assertEqual(result['file_types'],{'md':1});self.assertGreater(result['storage']['application_bytes'],0)
   store.sources.delete(source['id']);self.assertEqual(dashboard.snapshot(store)['counts']['documents'],0)
   with patch('dashboard.shutil.disk_usage',side_effect=OSError('unavailable')):
    result=dashboard.snapshot(store);self.assertIsNone(result['storage']['volume']);self.assertTrue(result['warnings'])
