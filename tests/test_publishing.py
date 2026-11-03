"""Acceptance checks for reader-safe output, dated selection and reusable layouts."""
import copy
import io
from pathlib import Path
import tempfile
import unittest
import zipfile

from docx import Document
from docx.shared import RGBColor
from PIL import Image
from pptx import Presentation
from pptx.util import Inches
from pypdf import PdfReader

import app
import editorial
import markdown_tools
import publication
import renderers


def office_parts(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        return "\n".join(archive.read(name).decode("utf-8") for name in archive.namelist()
                         if name.endswith((".xml", ".rels")))


class PublishingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = app.Store(Path(self.temp.name) / "publishing.sqlite3")
        self.outline = app.new_outline("Publishing test")
        self.outline["chapters"] = [app.chapter("Vertrag", mandatory=True)]
        self.text = dict(app.block(), text="Öffnen Sie den Vertrag.", status="Freigegeben")
        self.outline["chapters"][0]["blocks"] = [self.text]
        self.outline = self.store.save(self.outline)

    def tearDown(self):
        self.temp.cleanup()

    def test_jira_evidence_remains_internal_in_all_four_actual_artifacts(self):
        b = self.outline["chapters"][0]["blocks"][0]
        b.update(text="Öffnen Sie den Vertrag. SCM-123\n[Interner Beleg](https://jira.example/browse/SCM-123?focusedCommentId=7)\nUnabhängige Kennung ISO-9001 bleibt.",
                 text_format="markdown", source="https://jira.example/browse/SCM-123", note="PRIVATE_BLOCK_NOTE",
                 evidence=[{"key": "SCM-123", "status": "PRIVATE_JIRA_STATUS", "type": "PRIVATE_JIRA_TYPE",
                            "date": "2026-10-29", "verified": True, "note": "PRIVATE_EVIDENCE_NOTE"}])
        self.outline["metadata"]["version"] = "Release SCM-123"
        saved = self.store.save(self.outline)
        plan = app.compose(saved, saved["profile"])
        self.assertIn("SCM-123", saved["chapters"][0]["blocks"][0]["evidence"][0]["key"])
        outputs = [office_parts(app.office_export(plan, fmt)) for fmt in ["docx", "pptx"]]
        outputs.append(renderers.html_export(plan).decode())
        pdf = renderers.pdf_export(plan)
        self.assertTrue(pdf.startswith(b"%PDF-"))
        outputs.append("\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages))
        for output in outputs:
            self.assertIn("Vertrag", output)
            self.assertIn("ISO-9001", output)
            for private in ["SCM-123", "jira.example", "PRIVATE_BLOCK_NOTE", "PRIVATE_JIRA_STATUS", "PRIVATE_JIRA_TYPE", "PRIVATE_EVIDENCE_NOTE"]:
                self.assertNotIn(private, output)

    def test_unverified_evidence_blocks_release_without_hiding_editorial_record(self):
        b = self.outline["chapters"][0]["blocks"][0]
        b["evidence"] = [{"key": "SCM-42", "verified": False}]
        self.outline["chapters"][0]["config"]["status"] = "Freigegeben"
        saved = self.store.save(self.outline)
        plan = app.compose(saved, saved["profile"])
        self.assertTrue(any("nachweis" in error.lower() for error in editorial.release_errors(plan)))
        with self.assertRaises(app.Invalid):
            self.store.save(saved, releasing=True)
        saved["chapters"][0]["blocks"][0]["evidence"][0].update(verified=True, status="Done", type="Story", date="2026-11-03")
        released = self.store.save(saved, releasing=True)
        self.assertEqual(released["metadata"]["status"], "Freigegeben")

    def test_suitability_matrix_obeys_both_document_type_and_profile(self):
        b = self.outline["chapters"][0]["blocks"][0]
        b["uses"] = {"Handbuch": True, "Releaseletter": False, "Quickreference": True}
        saved = self.store.save(self.outline)
        row = publication.matrix(saved)["rows"][0]
        self.assertTrue(row["uses"]["Handbuch"]["included"])
        self.assertFalse(row["uses"]["Releaseletter"]["included"])
        self.assertTrue(row["uses"]["Quickreference"]["included"])
        saved["chapters"][0]["blocks"][0]["role"] = "HQ"
        self.assertFalse(any(v["included"] for v in publication.matrix(saved)["rows"][0]["uses"].values()))

    def test_temporal_country_override_year_environment_and_inclusive_bounds(self):
        rules = publication.validate_rules([
            {"state": "Freigegeben", "version": "Blueprint"},
            {"market": "DE", "role": "Retailer", "division": "Van", "year": "2026",
             "environment": "prod", "from": "2026-11-01", "until": "2026-11-30", "state": "Zurückgezogen", "version": "2.0"},
        ])
        p = dict(app.profile(), market="DE", as_of="2026-11-01")
        self.assertFalse(publication.effective(rules, p)["matches"])
        self.assertFalse(publication.effective(rules, dict(p, as_of="2026-11-30"))["matches"])
        for other in [dict(p, as_of="2026-12-01"), dict(p, market="FR"), dict(p, role="HQ"),
                      dict(p, division="PC"), dict(p, environment="preprod"), dict(p, as_of="2027-11-01")]:
            self.assertEqual(publication.effective(rules, other)["version"], "Blueprint")
        self.assertFalse(publication.effective(rules, dict(p, as_of=""))["matches"])

    def test_conflicting_time_rules_are_not_silently_picked_and_draft_not_promoted(self):
        rules = publication.validate_rules([{"market": "DE", "state": "Freigegeben", "version": "1"},
                                            {"market": "DE", "state": "Zurückgezogen", "version": "1"}])
        p = dict(app.profile(), market="DE", as_of="2026-11-03")
        decision = publication.effective(rules, p)
        self.assertFalse(decision["matches"])
        self.assertTrue(decision["conflict"])
        self.outline["profile"] = p
        b = self.outline["chapters"][0]["blocks"][0]
        b["validity"] = rules
        saved = self.store.save(self.outline)
        self.assertTrue(any("Widersprüch" in w for w in app.compose(saved, p)["warnings"]))
        saved["chapters"][0]["blocks"][0].update(status="Entwurf", validity=publication.validate_rules([{"state": "Freigegeben"}]))
        plan = app.compose(saved, p)
        self.assertEqual(plan["chapters"][0]["blocks"][0]["status"], "Entwurf")
        self.assertTrue(editorial.release_errors(plan))

    def test_time_and_evidence_input_validation(self):
        for value in ["2026-02-30", "20261103", "2026-1-01"]:
            with self.assertRaises(app.Invalid): publication.iso_date(value, "Datum")
        with self.assertRaises(app.Invalid): publication.validate_rules([{"from": "2026-12-01", "until": "2026-11-01"}])
        with self.assertRaises(app.Invalid): publication.validate_rules([{"year": "2300"}])
        with self.assertRaises(app.Invalid): publication.validate_evidence([{"key": "SCM-1"}, {"key": "scm-1"}])

    def test_markdown_batch_preserves_editable_structure_and_duplicate_filenames(self):
        source = "# Titel\n\n**Fett** und *kursiv*, [Handbuch](https://example.org/manual).\n\n3. Dritter Schritt\n4. Vierter Schritt\n\n| A | B |\n|---|---|\n| Eins | Zwei |\n\n```python\nprint('Hallo')\n```\n\n![Screen](https://external.invalid/private.png)"
        raw, fmt = markdown_tools.batch([{"name": "a.md", "text": source}, {"name": "a.md", "text": "# Zweite Datei"}])
        self.assertEqual(fmt, "zip")
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            self.assertEqual(len(set(names)), 2)
            doc = Document(io.BytesIO(archive.read(names[0])))
        self.assertEqual(len(doc.tables), 1)
        self.assertEqual(doc.tables[0].cell(1, 1).text, "Zwei")
        self.assertTrue(any(p.style.name == "Heading 1" and p.text == "Titel" for p in doc.paragraphs))
        self.assertTrue(any(r.bold and r.text == "Fett" for p in doc.paragraphs for r in p.runs))
        self.assertTrue(any(r.italic and r.text == "kursiv" for p in doc.paragraphs for r in p.runs))
        self.assertIn("3. Dritter Schritt", [p.text for p in doc.paragraphs])
        self.assertTrue(any("lokale Medienzuordnung" in p.text for p in doc.paragraphs))
        self.assertFalse(doc.inline_shapes)
        combined, fmt = markdown_tools.batch([{"name": "a.md", "text": source}, {"name": "b.md", "text": "# Ende"}], combined=True)
        self.assertEqual(fmt, "docx")
        text = "\n".join(p.text for p in Document(io.BytesIO(combined)).paragraphs)
        self.assertIn("Titel", text); self.assertIn("Ende", text)

    def test_html_contains_no_executable_raw_markup_or_remote_image(self):
        b = self.outline["chapters"][0]["blocks"][0]
        b.update(text_format="markdown", text='<script>alert(1)</script>\n\n![X](https://external.invalid/track)\n\n[Unsafe](javascript:alert(1))')
        plan = app.compose(self.outline, self.outline["profile"])
        html = renderers.html_export(plan).decode()
        self.assertNotIn("<script>", html)
        self.assertNotIn('<img src="https://', html)
        self.assertNotIn('href="javascript:', html)
        self.assertIn("Content-Security-Policy", html)

    def test_native_word_template_preserves_brand_but_removes_examples_and_assets(self):
        doc = Document()
        doc.styles["Heading 1"].font.color.rgb = RGBColor(10, 20, 30)
        doc.sections[0].header.paragraphs[0].text = "PUBLIC_BRAND_HEADER"
        doc.add_paragraph("PRIVATE_TEMPLATE_EXAMPLE")
        image = io.BytesIO(); Image.new("RGB", (10, 10), "red").save(image, format="PNG")
        doc.add_picture(io.BytesIO(image.getvalue()))
        raw = io.BytesIO(); doc.save(raw)
        entry = self.store.layouts.upload({"format": "docx", "name": "Brand", "version": "2026.11"}, raw.getvalue())
        _, template = self.store.layouts.snapshot(entry, "docx")
        plan = app.compose(self.outline, self.outline["profile"])
        artifact = app.office_export(plan, "docx", template_bytes=template)
        xml = office_parts(artifact)
        self.assertIn("PUBLIC_BRAND_HEADER", xml)
        self.assertNotIn("PRIVATE_TEMPLATE_EXAMPLE", xml)
        with zipfile.ZipFile(io.BytesIO(artifact)) as archive:
            self.assertFalse(any("/media/" in name for name in archive.namelist()))
        restored = Document(io.BytesIO(artifact))
        self.assertEqual(str(restored.styles["Heading 1"].font.color.rgb), "0A141E")

    def test_powerpoint_template_geometry_and_version_are_pinned(self):
        prs = Presentation(); prs.slide_width = Inches(10); prs.slide_height = Inches(7.5)
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        slide.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(1)).text = "PRIVATE_SLIDE_EXAMPLE"
        raw = io.BytesIO(); prs.save(raw)
        entry = self.store.layouts.upload({"format": "pptx", "name": "Deck", "version": "1"}, raw.getvalue())
        self.outline["layout"] = {"pptx": {"id": entry["id"], "revision": 1}}
        saved = self.store.save(self.outline)
        next_entry = self.store.layouts.upload({"id": entry["id"], "revision": 1, "format": "pptx", "name": "Deck", "version": "2"}, raw.getvalue())
        self.assertEqual(next_entry["revision"], 2)
        self.assertEqual(saved["layout"]["pptx"]["revision"], 1)
        artifact = app.office_export(app.compose(saved, saved["profile"]), "pptx", template_bytes=raw.getvalue())
        self.assertNotIn("PRIVATE_SLIDE_EXAMPLE", office_parts(artifact))
        generated = Presentation(io.BytesIO(artifact))
        self.assertEqual(generated.slide_width, Inches(10))
        for slide in generated.slides:
            for shape in slide.shapes:
                self.assertLessEqual(shape.left + shape.width, generated.slide_width + Inches(.01))
        with self.assertRaises(app.Conflict):
            self.store.layouts.upload({"id": entry["id"], "revision": 1, "format": "pptx", "name": "Stale"}, raw.getvalue())

    def test_image_upload_metadata_is_initial_and_duplicates_do_not_overwrite(self):
        raw = io.BytesIO(); Image.new("RGB", (20, 20), "blue").save(raw, format="PNG")
        metadata = {"market": "DE", "role": "Retailer", "division": "Van", "scope": "Kompakt", "priority": "Hoch",
                    "classification": {"roles": [], "domain_ids": [], "keywords": [], "labels": ["Release 2026"], "topic": ""}}
        asset = self.store.media.upload(raw.getvalue(), "Screen", "de", metadata)
        self.assertEqual(asset["priority"], "Hoch")
        self.assertEqual(asset["profile"]["market"], "DE")
        self.assertEqual(asset["classification"]["labels"], ["Release 2026"])
        self.assertFalse(asset["pii_reviewed"])
        other = self.store.media.upload(raw.getvalue(), "Duplicate", "fr", {"priority": "Niedrig"})
        self.assertEqual(other["id"], asset["id"])
        self.assertEqual(other["priority"], "Hoch")

    def test_html_disguised_doc_export_is_ingested_without_direct_connection(self):
        source = self.store.sources.upload("Jira.doc", b'<html><body><h1>SCM-456</h1><p>Contract management</p><script>PRIVATE_SCRIPT</script></body></html>', {"kind": "Jira", "origin": "Manueller Export"})
        chunks = self.store.sources.chunks(source["id"])
        self.assertIn("SCM-456", chunks[0]["text"])
        self.assertNotIn("PRIVATE_SCRIPT", chunks[0]["text"])


if __name__ == "__main__":
    unittest.main()
