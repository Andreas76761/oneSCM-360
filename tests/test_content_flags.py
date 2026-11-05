import tempfile
import unittest
from pathlib import Path
import app
from content_flags import detect
class FlagTests(unittest.TestCase):
 def test_detection_and_ambiguity(self):
  self.assertEqual(detect('The contract is for the customer and the user in this market.','Manual_v1.2_2026-11-05')['language'],'en')
  self.assertEqual(detect('Le contrat est pour le client et la société dans le marché.')['language'],'fr')
  self.assertEqual(detect('Der Vertrag ist für den Kunden und die Firma im Markt.')['language'],'de')
  self.assertEqual(detect('SCM-123')['language'],'')
  d=detect('Version 1.2 am 05.11.2026; Version 1.3 am 06.11.2026');self.assertEqual(d['date'],'');self.assertEqual(d['version'],'')
 def test_internal_persistence_revision_and_deleted_source(self):
  with tempfile.TemporaryDirectory() as folder:
   s=app.Store(Path(folder)/'db.sqlite3');source=s.sources.upload('Manual_v1.2_2026-11-05.md',b'The contract is for the customer and the user in this market.',{})
   r=s.content_flags.listing()[0];data={**r,'revision':0,'action':'analyse'}
   f=s.content_flags.process(data);self.assertTrue(f['internal']);self.assertEqual(f['date'],'2026-11-05');self.assertEqual(f['version'],'1.2')
   with self.assertRaises(app.Conflict):s.content_flags.process(data)
   s.content_flags.process({**data,'revision':1,'action':'save','language':'en','date':'2026-11-05','version':'1.2','reviewed':True})
   self.assertEqual(s.content_flags.listing()[0]['flags']['status'],'Bestätigt')
   self.assertEqual(s.all(),[])
   s.sources.delete(source['id']);self.assertEqual(s.content_flags.listing(),[])
