import io,unittest
import app,renderers
from pii_audit import findings,uncovered_regions
class PIITests(unittest.TestCase):
 def test_candidates_and_neutral_text(self):
  for text in ['Kontakt: person@example.org','IBAN: DE89370400440532013000','UserID: abc123','Name: Max Muster','+49 123 4567890']:
   self.assertTrue(findings(text),text)
  self.assertEqual(findings('Vertrag öffnen. Version 1.2, Release 2026-11.'),[])
 def test_all_renderers_block_pii_and_ignore_internal_note(self):
  o=app.new_outline('Test');o['chapters']=[app.chapter('Kapitel')];o['chapters'][0]['blocks']=[dict(app.block(),text='Kontakt person@example.org',status='Freigegeben')]
  plan=app.compose(o,o['profile'])
  for export in [lambda p:app.office_export(p,'docx'),lambda p:app.office_export(p,'pptx'),renderers.html_export,renderers.pdf_export]:
   with self.assertRaises(app.Invalid):export(plan)
  o['chapters'][0]['blocks'][0].update(text='Vertrag öffnen.',note='person@example.org')
  self.assertTrue(renderers.html_export(app.compose(o,o['profile'])))
 def test_image_region_requires_full_coverage(self):
  ocr={'candidate_regions':[{'x':10,'y':10,'w':20,'h':10}]}
  self.assertTrue(uncovered_regions(ocr,{'redactions':[]}))
  self.assertFalse(uncovered_regions(ocr,{'redactions':[{'x':0,'y':0,'w':40,'h':40}]}))
