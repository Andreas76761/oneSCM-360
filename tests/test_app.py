import base64
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from docx import Document
from pptx import Presentation

import app


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = app.Store(Path(self.temp.name) / "test.sqlite3")
        self.outline = app.new_outline("Retailer-Handbuch")
        self.content = app.block()
        self.content["text"] = "Vertrag öffnen und Angaben prüfen."
        self.content["note"] = "Interne Rückfrage zur Prozessbeschreibung."
        self.outline["chapters"][0]["blocks"].append(self.content)

    def tearDown(self):
        self.temp.cleanup()

    def test_import_hierarchy_and_mandatory(self):
        rows, warnings = app.parse_outline("1 Einleitung\n2 Contract Management\n2.1 Übersicht\n2.1.1 Details\n3 FAQ")
        self.assertEqual([c["level"] for c in rows], [1, 1, 2, 3, 1])
        self.assertTrue(rows[0]["mandatory"])
        self.assertTrue(rows[-1]["mandatory"])
        self.assertEqual(warnings, [])

    def test_import_normalizes_skipped_levels_with_warning(self):
        rows, warnings = app.parse_outline("### Einstieg\n###### Detail")
        self.assertEqual([c["level"] for c in rows], [1, 2])
        self.assertEqual(len(warnings), 2)

    def test_docx_import_uses_headings_not_body(self):
        doc = Document()
        doc.add_heading("Einleitung", 1)
        doc.add_paragraph("Dies ist Fließtext und kein Kapitel.")
        doc.add_heading("Voraussetzungen", 2)
        buffer = io.BytesIO()
        doc.save(buffer)
        rows, warnings = app.parse_docx(buffer.getvalue())
        self.assertEqual([r["title"] for r in rows], ["Einleitung", "Voraussetzungen"])
        self.assertEqual([r["level"] for r in rows], [1, 2])

    def test_revisions_preserve_ids_and_reject_stale_writes(self):
        saved = self.store.save(self.outline)
        first = json.loads(json.dumps(saved))
        saved["chapters"][0]["title"] = "Einführung"
        second = self.store.save(saved)
        self.assertEqual(second["revision"], 2)
        self.assertEqual(first["chapters"][0]["id"], second["chapters"][0]["id"])
        with self.assertRaises(app.Conflict):
            self.store.save(first)
        reopened = app.Store(self.store.path).get(second["id"])
        self.assertEqual(reopened, second)
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM history").fetchone()[0], 2)

    def test_filters_and_internal_notes_are_independent(self):
        p = app.profile()
        p["show_notes"] = True
        plan = app.compose(self.outline, p)
        self.assertEqual(plan["chapters"][0]["blocks"][0]["note"], "")
        self.assertTrue(plan["warnings"])
        self.content["internal"] = True
        self.assertEqual(app.compose(self.outline, p)["chapters"][0]["blocks"], [])
        p["role"] = "HQ"
        self.assertEqual(app.compose(self.outline, p)["chapters"][0]["blocks"][0]["note"], self.content["note"])
        p["show_notes"] = False
        self.assertEqual(app.compose(self.outline, p)["chapters"][0]["blocks"][0]["note"], "")

    def test_all_selection_dimensions(self):
        p = app.profile()
        for key, wrong in [("role", "MO"), ("scope", "Kompakt"), ("market", "FR"),
                           ("division", "PC"), ("language", "fr"), ("release", "R2")]:
            b = app.block()
            b["text"] = "Inhalt"
            b[key] = wrong
            self.assertIsNotNone(app.exclusion(b, p), key)
        b = app.block()
        b["text"] = "Inhalt"
        b["market"] = ""
        self.assertIn("ungeklärt", app.exclusion(b, p))
        b["market"] = "*"
        p["approved_only"] = True
        self.assertIsNotNone(app.exclusion(b, p))
        b["status"] = "Freigegeben"
        self.assertIsNone(app.exclusion(b, p))

    def test_combined_division_retains_both_variants(self):
        self.content["division"] = "PC"
        p = app.profile()
        self.assertFalse(app.compose(self.outline, p)["chapters"][0]["blocks"])
        p["division"] = "Beide"
        self.assertEqual(app.compose(self.outline, p)["chapters"][0]["blocks"][0]["division"], "PC")

    def test_ancestors_kept_and_numbering_has_no_gaps(self):
        parent = app.chapter("Contract Management")
        child = app.chapter("Vertrag öffnen", 2)
        child["blocks"] = [self.content]
        skipped = app.chapter("Nicht relevant")
        self.outline["chapters"] = [skipped, parent, child]
        rows = app.compose(self.outline, app.profile())["chapters"]
        self.assertEqual([r["visible"] for r in rows], [False, True, True])
        self.assertEqual([r["number"] for r in rows], ["", "1", "1.1"])

    def test_invalid_tree_does_not_mutate_database(self):
        self.outline["chapters"][0]["level"] = 2
        with self.assertRaises(app.Invalid):
            self.store.save(self.outline)
        self.assertEqual(self.store.all(), [])

    def test_office_exports_contain_selected_text_but_no_notes(self):
        self.content["text"] = "Beginn " + "Ausführliche Anleitung. " * 200 + "Endmarkierung"
        self.outline = self.store.save(self.outline)
        plan = app.compose(self.outline, app.profile())
        for fmt in ["docx", "pptx"]:
            data = app.office_export(plan, fmt)
            if fmt == "docx":
                obj = Document(io.BytesIO(data))
                text = "\n".join(p.text for p in obj.paragraphs)
            else:
                obj = Presentation(io.BytesIO(data))
                text = "\n".join(s.text for page in obj.slides for s in page.shapes if s.has_text_frame)
                self.assertGreater(len(obj.slides), 4)
            self.assertIn("Endmarkierung", text)
            self.assertNotIn("Interne Rückfrage", text)
            self.assertIn("PRÜFAUSGABE", text)
            eid = self.store.record_export(plan, fmt, data)
            with self.store.connect() as db:
                self.assertEqual(db.execute("SELECT artifact FROM exports WHERE id=?", (eid,)).fetchone()[0], data)


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = app.Store(Path(self.temp.name) / "http.sqlite3")
        self.server = app.make_server(self.store, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        with urlopen(self.base + "/api/state") as response:
            self.state = json.load(response)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def post(self, path, data, token=True):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Local-Token"] = self.state["token"]
        return urlopen(Request(self.base + path, json.dumps(data).encode(), headers))

    def test_create_save_export_and_missing_token(self):
        with self.assertRaises(HTTPError) as failure:
            self.post("/api/create", {"title": "Unzulässig"}, token=False)
        self.assertEqual(failure.exception.code, 403)
        with self.post("/api/create", {"title": "HTTP-Test"}) as response:
            outline = json.load(response)
        b = app.block()
        b["text"] = "Funktionaler HTTP-Test"
        outline["chapters"][0]["blocks"].append(b)
        with self.post("/api/save", outline) as response:
            saved = json.load(response)
        with self.post("/api/export", {"id": saved["id"], "revision": saved["revision"], "format": "docx"}) as response:
            doc = Document(io.BytesIO(response.read()))
        self.assertIn("Funktionaler HTTP-Test", "\n".join(p.text for p in doc.paragraphs))

    def test_cross_origin_mutation_is_denied(self):
        request = Request(self.base + "/api/create", b'{"title":"test"}',
                          {"X-Local-Token": self.state["token"], "Origin": "https://other.example"})
        with self.assertRaises(HTTPError) as failure:
            urlopen(request)
        self.assertEqual(failure.exception.code, 403)

    def test_history_copy_and_compare_endpoints(self):
        with self.post("/api/create", {"title": "Vergleich"}) as response:
            left = json.load(response)
        with self.post("/api/copy", {"id": left["id"]}) as response:
            right = json.load(response)
        right["metadata"]["version"] = "2.0"
        right["chapters"][0]["title"] = "Neue Einleitung"
        with self.post("/api/save", right) as response:
            right = json.load(response)
        with self.post("/api/history", {"id": right["id"]}) as response:
            self.assertEqual(len(json.load(response)), 2)
        with self.post("/api/compare", {"left_id": left["id"], "right_id": right["id"], "right_revision": 2}) as response:
            self.assertEqual(json.load(response)["counts"]["renamed"], 1)
        with self.assertRaises(HTTPError) as failure:
            self.post("/api/compare", {"left_id": left["id"], "right_id": right["id"], "right_revision": 99})
        self.assertEqual(failure.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
