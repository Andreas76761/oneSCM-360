import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from docx import Document
from pptx import Presentation
from pypdf import PdfWriter

import app
import domain_mapping as dm
import sources


class SourcesMappingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = app.Store(Path(self.temp.name) / "source.sqlite3")
        self.outline = app.new_outline("Handbuch")
        self.outline["chapters"] = [app.chapter("Vertrag prüfen"), app.chapter("Details", 2)]
        self.outline = self.store.save(self.outline)

    def tearDown(self):
        self.temp.cleanup()

    def upload(self, text="Retailer Vertrag prüfen. Finance Rechnung für den Markt."):
        return self.store.sources.upload("Jira.txt", text.encode(), {"kind": "Jira", "release": "R1"})

    def test_legacy_mapping_is_migrated_without_changing_history(self):
        data = app.new_outline("Alt")
        data["chapters"][0]["domain"] = "Contract Management"
        data["revision"] = 1
        raw = json.dumps(data)
        with self.store.connect() as db:
            db.execute("INSERT INTO outlines VALUES(?,?,?)", (data["id"], 1, raw))
            db.execute("INSERT INTO history VALUES(?,?,?,?)", (data["id"], 1, app.now(), raw))
        hydrated = self.store.get(data["id"])
        self.assertEqual(hydrated["chapters"][0]["mappings"], [{"target_id": "d3", "active": True}])
        hydrated["chapters"][0]["mappings"] = []
        saved = self.store.save(hydrated)
        self.assertEqual(self.store.get(saved["id"])["chapters"][0]["mappings"], [])
        self.assertEqual(self.store.snapshot(saved["id"], 1)["chapters"][0]["mappings"][0]["target_id"], "d3")

    def test_many_to_many_active_controls_and_unique_counts(self):
        a, b = self.outline["chapters"]
        a["mappings"] = [{"target_id": "d3", "active": True}, {"target_id": "d5", "active": True}]
        b["mappings"] = [{"target_id": "d3", "active": True}]
        self.outline = self.store.save(self.outline)
        grouped = dm.grouped(self.outline, dm.catalog())
        self.assertEqual(grouped["groups"][2]["chapter_count"], 2)
        self.assertEqual(grouped["groups"][4]["chapter_count"], 1)
        self.assertEqual(grouped["active"], 3)
        self.outline["mapping_enabled"] = False
        self.assertEqual(dm.grouped(self.outline, dm.catalog())["groups"][2]["chapter_count"], 0)
        paused = dm.grouped(self.outline, dm.catalog(), True)
        self.assertEqual(paused["groups"][2]["chapter_count"], 2)
        self.assertEqual(paused["active"], 0)
        self.assertEqual(paused["total"], 3)

    def test_subdomain_validation_snapshot_and_comparison(self):
        taxonomy = self.store.save_taxonomy({"revision": 0, "subdomains": [{"id": "sub1", "name": "Verlängerung", "parent_id": "d3"}]})
        self.outline["chapters"][0]["mappings"] = [{"target_id": "d3", "active": True}, {"target_id": "sub1", "active": True}]
        saved = self.store.save(self.outline)
        grouped = dm.grouped(saved, dm.catalog(taxonomy["subdomains"]))
        self.assertEqual(grouped["groups"][2]["chapter_count"], 1)
        self.assertEqual(grouped["groups"][2]["mapping_count"], 2)
        taxonomy["subdomains"][0]["name"] = "Laufzeitverlängerung"
        self.store.save_taxonomy(taxonomy)
        newer = self.store.save(saved)
        result = app.compare_outlines(saved, newer)
        self.assertIn("mappings", result["left"][0]["changed_fields"])
        self.assertEqual(self.store.snapshot(saved["id"], saved["revision"])["domain_catalog"][-1]["name"], "Verlängerung")
        with self.assertRaises(app.Conflict):
            self.store.save_taxonomy(taxonomy)
        with self.assertRaises(ValueError):
            self.store.save_taxonomy({"revision": 2, "subdomains": []})

    def test_invalid_and_duplicate_mappings_rejected(self):
        self.outline["chapters"][0]["mappings"] = [{"target_id": "missing", "active": True}]
        with self.assertRaises(ValueError):
            self.store.save(self.outline)
        with self.assertRaises(ValueError):
            dm.validate_mappings([{"target_id": "d1", "active": True}] * 2)

    def test_upload_deduplicates_and_keeps_fundstelle(self):
        result = self.upload()
        self.assertFalse(result["duplicate"])
        self.assertTrue(self.upload()["duplicate"])
        self.assertEqual(len(self.store.sources.listing()), 1)
        chunk = self.store.sources.chunks(result["id"])[0]
        self.assertEqual(chunk["location"], "Text")
        self.assertIn("Retailer", chunk["text"])
        self.assertEqual(chunk["suggestion"], {})

    def test_supported_extractors(self):
        doc = Document()
        doc.add_paragraph("Dealer Vertrag prüfen")
        doc.add_table(rows=1, cols=1).cell(0, 0).text = "Rechnung"
        raw = io.BytesIO()
        doc.save(raw)
        chunks, _ = sources.extract("test.docx", raw.getvalue())
        self.assertIn("Rechnung", " ".join(c["text"] for c in chunks))
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = "Contract Management"
        raw = io.BytesIO()
        prs.save(raw)
        chunks, _ = sources.extract("test.pptx", raw.getvalue())
        self.assertEqual(chunks[0]["location"], "Folie 1")
        self.assertIn("Contract Management", chunks[0]["text"])
        chunks, _ = sources.extract("test.html", b'<h1>Vertrag</h1><script>do_not_run()</script><p>Retailer</p>')
        self.assertNotIn("do_not_run", chunks[0]["text"])
        chunks, _ = sources.extract("jira.csv", b'Key;Summary\nABC-1;Dealer Vertrag\n')
        self.assertEqual(chunks[0]["location"], "CSV-Zeile 2")
        self.assertIn("ABC-1", chunks[0]["text"])
        chunks, _ = sources.extract("data.json", b'[{"text":"Vertrag"}]')
        self.assertEqual(chunks[0]["location"], "JSON-Eintrag 1")
        writer, raw = PdfWriter(), io.BytesIO()
        writer.add_blank_page(width=100, height=100)
        writer.write(raw)
        chunks, warnings = sources.extract("scan.pdf", raw.getvalue())
        self.assertEqual(chunks, [])
        self.assertTrue(any("OCR" in warning for warning in warnings))
        from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
        writer, raw = PdfWriter(), io.BytesIO()
        page = writer.add_blank_page(width=595, height=842)
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(b"BT /F1 12 Tf 72 720 Td (Retailer Vertrag pruefen) Tj ET")
        page[NameObject("/Contents")] = writer._add_object(stream)
        writer.write(raw)
        chunks, _ = sources.extract("manual.pdf", raw.getvalue())
        self.assertIn("Retailer Vertrag", chunks[0]["text"])
        self.assertEqual(chunks[0]["location"], "Seite 1")

    def test_local_triage_proposes_without_assigning_or_overwriting_review(self):
        sid = self.upload()["id"]
        result = self.store.sources.triage(sid, self.outline, dm.catalog(), "rules", "", 0)
        self.assertTrue(result["done"])
        chunk = self.store.sources.chunks(sid)[0]
        self.assertIn("Retailer", chunk["suggestion"]["roles"])
        self.assertIn("d3", chunk["suggestion"]["domain_ids"])
        self.assertIn(self.outline["chapters"][0]["id"], chunk["suggestion"]["chapter_ids"])
        self.assertEqual(chunk["assignments"], [])
        self.assertEqual(chunk["labels"], {})
        self.store.sources.review({"id": chunk["id"], "revision": chunk["revision"], "labels": {"roles": ["HQ"]}, "assignments": []}, {"d3"})
        self.store.sources.triage(sid, self.outline, dm.catalog(), "rules", "", 0)
        self.assertEqual(self.store.sources.chunks(sid)[0]["labels"]["roles"], ["HQ"])

    def test_review_counts_delete_and_stale_edit(self):
        sid = self.upload()["id"]
        c = self.store.sources.chunks(sid)[0]
        request = {"id": c["id"], "revision": 1, "labels": {"roles": ["Retailer"], "domain_ids": ["d3"]},
                   "assignments": [{"outline_id": self.outline["id"], "chapter_id": ch["id"]} for ch in self.outline["chapters"]]}
        self.store.sources.review(request, {"d3"})
        with self.assertRaises(ValueError):
            self.store.sources.review(request, {"d3"})
        index = self.store.sources.index()
        self.assertEqual(len(index), 1)
        self.assertEqual(len(index[0]["assignments"]), 2)
        self.outline = self.store.save(self.outline)
        self.assertEqual(len(self.store.sources.index()[0]["assignments"]), 2)
        self.outline["chapters"].pop()
        self.store.save(self.outline)
        self.assertEqual(len(self.store.sources.index()[0]["assignments"]), 1)
        self.store.sources.delete(sid)
        self.assertEqual(self.store.sources.index(), [])
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM assignments").fetchone()[0], 0)

    def test_outline_copy_keeps_chunk_links(self):
        sid = self.upload()["id"]
        c = self.store.sources.chunks(sid)[0]
        self.store.sources.review({"id": c["id"], "revision": 1, "labels": {"roles": ["Retailer"]},
                                   "assignments": [{"outline_id": self.outline["id"], "chapter_id": self.outline["chapters"][0]["id"]}]}, set())
        copied = self.store.copy(self.outline["id"])
        links = self.store.sources.index()[0]["assignments"]
        self.assertEqual(len(links), 2)
        self.assertIn({"outline_id": copied["id"], "chapter_id": copied["chapters"][0]["id"]}, links)

    def test_ollama_adapter_validates_model_result_and_does_not_fallback(self):
        chunk = {"text": "Retailer Vertrag"}
        result = {"roles": ["Retailer"], "domain_ids": ["d3"], "keywords": ["Vertrag"], "labels": [], "topic": "Vertrag", "chapter_ids": [self.outline["chapters"][0]["id"]]}
        connection = Mock()
        response = connection.getresponse.return_value
        response.status = 200
        response.read.return_value = json.dumps({"response": json.dumps(result)}).encode()
        with patch("sources.http.client.HTTPConnection", return_value=connection):
            suggestion = sources.ollama_suggestion(chunk, self.outline, dm.catalog(), "local-model")
        self.assertEqual(suggestion["method"], "Ollama: local-model")
        result["chapter_ids"] = ["invented"]
        response.read.return_value = json.dumps({"response": json.dumps(result)}).encode()
        with patch("sources.http.client.HTTPConnection", return_value=connection), self.assertRaises(ValueError):
            sources.ollama_suggestion(chunk, self.outline, dm.catalog(), "local-model")
        connection.request.side_effect = OSError("offline")
        with patch("sources.http.client.HTTPConnection", return_value=connection), self.assertRaises(ValueError):
            sources.ollama_suggestion(chunk, self.outline, dm.catalog(), "local-model")

    def test_internal_notes_never_enter_exports_even_for_hq(self):
        c = self.outline["chapters"][0]
        b = app.block()
        b["text"], b["note"] = "Öffentlicher Text", "SECRET-BLOCK-NOTE"
        c["blocks"] = [b]
        c["remarks"] = [{"id": "remark", "text": "SECRET-MATRIX-NOTE", "color": "rot", "role": "HQ", "domain_id": "d3"}]
        p = app.profile()
        p.update(role="HQ", show_notes=True)
        plan = app.compose(self.outline, p)
        self.assertNotIn("SECRET", json.dumps(plan))
        # The renderer itself also excludes legacy note fields.
        plan["chapters"][0]["blocks"][0]["note"] = "SECRET-LEGACY-NOTE"
        from zipfile import ZipFile
        for kind in ["docx", "pptx"]:
            raw = app.office_export(plan, kind)
            with ZipFile(io.BytesIO(raw)) as archive:
                texts = b" ".join(archive.read(name) for name in archive.namelist() if name.endswith(".xml"))
            self.assertNotIn(b"SECRET", texts)


if __name__ == "__main__":
    unittest.main()
