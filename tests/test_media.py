import copy
import io
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

from PIL import Image, ImageDraw, ImageFont
import app


def sample_image():
    image = Image.new("RGB", (800, 300), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 30)
    except OSError:
        font = ImageFont.load_default(size=30)
    draw.text((25, 40), "USERID: TEST123", fill="black", font=font)
    draw.text((25, 180), "Contract overview", fill="black", font=font)
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


class MediaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = app.Store(Path(self.temp.name) / "media.sqlite3")
        self.asset = self.store.media.upload(sample_image(), "Screen", "de")
        self.outline = app.new_outline("Bildhandbuch")
        self.outline["chapters"] = [app.chapter("Bildkapitel", mandatory=True)]

    def tearDown(self):
        self.temp.cleanup()

    def approve(self):
        a = copy.deepcopy(self.asset)
        a.update(pii_reviewed=True, status="Freigegeben", redactions=[{"x": 15, "y": 25, "w": 400, "h": 70, "mode": "mask"}],
                 markers=[{"x": 10, "y": 165, "w": 450, "h": 75, "text": "Schritt 1"}], note="SECRET_NOTE", caption="Vertragsübersicht")
        self.asset = self.store.media.save(a)
        return self.asset

    def assign(self, refs=None, kind="Bild"):
        refs = refs or [{"asset_id": self.asset["id"], "revision": self.asset["revision"]}]
        self.outline["chapters"][0]["media"] = [{"id": app.uid(), "title": "Vertragsablauf", "kind": kind,
            "conditions": {}, "note": "SECRET_ASSIGNMENT", "frames": [{"caption": "", "variants": refs}]}]
        self.outline = self.store.save(self.outline)
        return app.compose(self.outline, app.profile())

    def test_dedup_review_gate_original_rule_and_raster_redaction(self):
        duplicate = self.store.media.upload(sample_image(), "Doppelt")
        self.assertEqual(duplicate["id"], self.asset["id"])
        self.assertTrue(duplicate["duplicate"])
        with self.assertRaises(app.Invalid):
            self.store.media.image(self.asset["id"], 1, "Retailer", original=True)
        bad = dict(self.asset, status="Freigegeben")
        with self.assertRaises(app.Invalid):
            self.store.media.save(bad)
        self.approve()
        raw = self.store.media.image(self.asset["id"], 2, "Retailer")
        image = Image.open(io.BytesIO(raw))
        self.assertEqual(image.getpixel((30, 45)), (37, 59, 70))
        self.assertNotEqual(raw, self.store.media.original(self.asset["id"]))
        self.assertFalse(image.info)

    def test_missing_variant_and_incomplete_clickpath_block_release(self):
        plan = self.assign()
        self.assertFalse(plan["chapters"][0]["figures"])
        self.assertTrue(any("Bildfassung" in w for w in plan["warnings"]))
        self.approve()
        plan = self.assign(kind="Klickstrecke")
        self.assertTrue(plan["chapters"][0]["figures"])
        frames = self.outline["chapters"][0]["media"][0]["frames"]
        frames.append({"caption": "Fehlt", "variants": [{"asset_id": self.asset["id"], "revision": 1}]})
        self.outline = self.store.save(self.outline)
        plan = app.compose(self.outline, app.profile())
        self.assertFalse(plan["chapters"][0]["figures"])
        self.assertTrue(any("Schritt 2" in w for w in plan["warnings"]))

    def test_profile_variants_and_office_contain_only_redacted_pixels(self):
        self.approve()
        self.outline["chapters"][0]["config"] = {"expected": ["Bild"], "status": "Freigegeben"}
        plan = self.assign()
        self.assertEqual(plan["warnings"], [])
        self.assertEqual(plan["manifest"]["images"][0]["revision"], 2)
        original = self.store.media.original(self.asset["id"])
        redacted = self.store.media.image(self.asset["id"], 2, "Retailer")
        loader = lambda aid, rev: self.store.media.image(aid, rev, "Retailer")
        for fmt in ["docx", "pptx"]:
            artifact = app.office_export(plan, fmt, loader)
            with zipfile.ZipFile(io.BytesIO(artifact)) as archive:
                blobs = [archive.read(n) for n in archive.namelist() if "/media/" in n]
                self.assertIn(redacted, blobs)
                self.assertNotIn(original, blobs)
                xml = "".join(archive.read(n).decode() for n in archive.namelist() if n.endswith(".xml"))
                self.assertNotIn("SECRET_NOTE", xml)
                self.assertNotIn("SECRET_ASSIGNMENT", xml)
        changed = copy.deepcopy(self.asset)
        changed["profile"]["role"] = "HQ"
        updated = self.store.media.save(changed)
        # Earlier assignments and pixels are immutable.
        self.assertEqual(self.store.get(self.outline["id"])["chapters"][0]["media"][0]["frames"][0]["variants"][0]["revision"], 2)
        self.outline["chapters"][0]["media"][0]["frames"][0]["variants"] = [{"asset_id": updated["id"], "revision": 3}]
        self.outline = self.store.save(self.outline)
        self.assertTrue(app.compose(self.outline, app.profile())["warnings"])

    def test_invalid_regions_and_stale_revision_rejected(self):
        bad = dict(self.asset, redactions=[{"x": 790, "y": 0, "w": 100, "h": 50, "mode": "mask"}])
        with self.assertRaises(app.Invalid):
            self.store.media.save(bad)
        stale = copy.deepcopy(self.asset)
        self.approve()
        with self.assertRaises(app.Conflict):
            self.store.media.save(stale)

    def test_extract_embedded_docx_and_pptx_images_without_auto_approval(self):
        from docx import Document
        from pptx import Presentation
        from pptx.util import Inches
        doc = Document()
        doc.add_paragraph("Testtext")
        doc.add_picture(io.BytesIO(sample_image()))
        raw = io.BytesIO()
        doc.save(raw)
        source = self.store.sources.upload("test.docx", raw.getvalue(), {})
        result = self.store.media.extract_source(source["id"])
        self.assertEqual(len(result["images"]), 1)
        self.assertTrue(result["images"][0]["duplicate"])
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        slide.shapes.add_picture(io.BytesIO(sample_image()), Inches(1), Inches(1))
        raw = io.BytesIO()
        prs.save(raw)
        source = self.store.sources.upload("test.pptx", raw.getvalue(), {})
        self.assertEqual(len(self.store.media.extract_source(source["id"])["images"]), 1)
        self.assertFalse(self.store.media.listing()[0]["pii_reviewed"])
        raw = io.BytesIO()
        Image.open(io.BytesIO(sample_image())).save(raw, format="PDF")
        source = self.store.sources.upload("embedded.pdf", raw.getvalue(), {})
        self.assertEqual(len(self.store.media.extract_source(source["id"])["images"]), 1)

    def test_delete_unused_media_and_protect_historical_assignments(self):
        self.store.media.delete(self.asset["id"])
        self.assertEqual(self.store.media.listing(), [])
        self.asset = self.store.media.upload(sample_image(), "Screen", "de")
        self.approve()
        self.assign()
        self.outline["chapters"][0]["media"] = []
        self.store.save(self.outline)
        with self.assertRaises(app.Invalid):
            self.store.media.delete(self.asset["id"])

    @unittest.skipUnless(shutil.which("tesseract"), "Tesseract optional")
    def test_local_ocr_proposes_regions_without_approval(self):
        result = self.store.media.ocr(self.asset["id"])
        self.assertIn("USERID", result["text"])
        self.assertTrue(result["regions"])
        self.assertFalse(self.store.media.snapshot(self.asset["id"], 1)["pii_reviewed"])


if __name__ == "__main__":
    unittest.main()
