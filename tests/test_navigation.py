import tempfile,unittest
from pathlib import Path
import app,navigation
class NavigationTests(unittest.TestCase):
 def test_counts_follow_saved_data(self):
  with tempfile.TemporaryDirectory() as folder:
   s=app.Store(Path(folder)/'db.sqlite3');self.assertEqual(navigation.counts(s)['sources-button']['count'],0)
   a=s.sources.upload('a.md',b'# Title\nContent',{});s.save(app.new_outline('Manual'))
   result=navigation.counts(s);self.assertEqual(result['sources-button']['count'],1);self.assertEqual(result['markdown-tool']['count'],1);self.assertEqual(result['overview-button']['count'],1);self.assertIsNone(result['backup-button']['count'])
   s.sources.delete(a['id']);self.assertEqual(navigation.counts(s)['sources-button']['count'],0)
