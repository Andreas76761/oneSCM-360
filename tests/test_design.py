"""Design reaches actual artifacts while remaining bounded and reader-only."""
import io
import unittest
import zipfile
from pypdf import PdfReader
import app
import layouts
import renderers


def xml(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        return '\n'.join(z.read(n).decode() for n in z.namelist() if n.endswith('.xml'))


class DesignTests(unittest.TestCase):
    def plan(self):
        outline=app.new_outline('Gestaltung')
        outline['chapters']=[app.chapter('Kapitel',mandatory=True),app.chapter('Unterkapitel',level=2)]
        outline['chapters'][0]['blocks']=[dict(app.block(),text='Hinweis: Vertrag prüfen.\n\n[Tipp-Link](https://example.invalid)',text_format='markdown',status='Freigegeben')]
        outline['layout']={'theme':{'chapter':'#991122','subchapter':'#223399','notice':'#ccddee','keywords':['Vertrag'],'highlight':'#ffeedd','icon_style':'letters','page_numbers':True}}
        return app.compose(app.validate_outline(outline),outline['profile'])

    def test_word_html_pdf_and_powerpoint_design(self):
        plan=self.plan()
        word=xml(app.office_export(plan,'docx'))
        for value in ['991122','223399','CCDDEE','FFEEDD']:
            self.assertIn(value.lower(),word.lower())
        self.assertIn('PAGE',word)
        powerpoint=xml(app.office_export(plan,'pptx'))
        self.assertIn('991122',powerpoint.lower())
        self.assertIn('ffeedd',powerpoint.lower())
        html=renderers.html_export(plan).decode()
        self.assertIn('#991122',html)
        self.assertIn('<mark>Vertrag</mark>',html)
        pdf=renderers.pdf_export(plan)
        self.assertIn('Vertrag',' '.join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages))

    def test_invalid_theme_and_no_page_field(self):
        for theme in [{'icon_style':'unknown'},{'image_width':101},{'keywords':['a'*81]},{'chapter':'red'},{'page_numbers':'true'}]:
            with self.assertRaises(app.Invalid):layouts.theme(theme)
        plan=self.plan();plan['layout']['theme']['page_numbers']=False
        self.assertNotIn('w:instr="PAGE"',xml(app.office_export(plan,'docx')))

if __name__=='__main__':unittest.main()
