import io,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from PIL import Image
import app
class OCRTests(unittest.TestCase):
 def test_persistence_exclusion_revision_and_internal_search(self):
  with tempfile.TemporaryDirectory() as folder:
   store=app.Store(Path(folder)/'db.sqlite3');raw=io.BytesIO();Image.new('RGB',(300,200),'white').save(raw,format='PNG');a=store.media.upload(raw.getvalue(),'Contract','de',{})
   tsv='level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n'
   for i,(text,line,x) in enumerate([('Vertrag',1,0),('anlegen',1,60),('Name',2,0),('PrivatePerson',2,60)]):tsv+=f'5\t1\t1\t1\t{line}\t{i+1}\t{x}\t{line*20}\t50\t10\t90\t{text}\n'
   with patch('media.shutil.which',return_value='/test/tesseract'),patch('media.subprocess.run',return_value=SimpleNamespace(stdout=tsv.encode())):
    result=store.media.ocr(a['id'])
   saved=app.Store(Path(folder)/'db.sqlite3').ocr_records.get(a['id'])
   self.assertEqual(saved['text'],'Vertrag anlegen');self.assertEqual(len(saved['lines']),1);self.assertNotIn('PrivatePerson',str(saved))
   args={'query':'Vertrag','kind':'ocr','include_internal':True,'working_role':'intern'}
   self.assertEqual(store.rag.search(args)['total'],1)
   self.assertEqual(store.rag.search({**args,'include_internal':False})['total'],0)
   store.media.save(a);self.assertTrue(store.ocr_records.get(a['id'])['stale']);self.assertEqual(store.rag.search(args)['total'],0)
   store.media.delete(a['id']);self.assertIsNone(store.ocr_records.get(a['id']))
