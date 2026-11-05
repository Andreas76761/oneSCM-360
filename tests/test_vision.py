import io,unittest,importlib.util
from PIL import Image,ImageDraw
import vision
class VisionTests(unittest.TestCase):
 @unittest.skipUnless(importlib.util.find_spec('cv2'),'optional OpenCV not installed')
 def test_dimensions_and_regions_preserved(self):
  im=Image.new('RGB',(400,180),'white');ImageDraw.Draw(im).text((20,40),'Contract 123',fill='black');raw=io.BytesIO();im.save(raw,format='PNG')
  for mode in ['contrast','threshold']:
   output,meta=vision.prepare(raw.getvalue(),mode);self.assertEqual(Image.open(io.BytesIO(output)).size,im.size);self.assertEqual(meta['mode'],mode);self.assertLessEqual(len(meta['regions']),200)
   for r in meta['regions']:self.assertTrue(0<=r['x']<400 and 0<=r['y']<180)
 def test_invalid_mode(self):
  import app
  with self.assertRaises(app.Invalid):vision.prepare(b'', 'invalid')
 @unittest.skipUnless(importlib.util.find_spec('cv2'),'optional OpenCV not installed')
 def test_real_ocr_records_preprocessing(self):
  import tempfile,shutil,app
  from pathlib import Path
  if not shutil.which('tesseract'):self.skipTest('Tesseract not installed')
  im=Image.new('RGB',(600,200),'white');ImageDraw.Draw(im).text((30,50),'Contract Management',fill='black',font_size=32);raw=io.BytesIO();im.save(raw,format='PNG')
  with tempfile.TemporaryDirectory() as folder:
   s=app.Store(Path(folder)/'db.sqlite3');asset=s.media.upload(raw.getvalue(),'Test','en',{});before=s.media.original(asset['id']);result=s.media.ocr(asset['id'],'contrast')
   self.assertIn('OpenCV',result['analysis']['engine']);self.assertEqual(s.ocr_records.get(asset['id'])['analysis']['mode'],'contrast');self.assertEqual(before,s.media.original(asset['id']))
