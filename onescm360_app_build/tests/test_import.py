import io
import json
import re
import unittest
import zipfile

from helpers import CH01_HTML, AppCase, html_doc, html_table, make_docx, p


class ImportTests(AppCase, unittest.TestCase):
    def test_html_import_end_to_end(self):
        r = self.upload(CH01_HTML, "ch01.html")
        self.assertEqual(r.status_code, 201, r.get_json())
        rec = r.get_json()["importRecord"]
        self.assertRegex(rec["importId"], r"^IMP-\d{8}-\d{6}-[A-F0-9]{6}$")
        self.assertEqual(rec["status"], "COMPLETED")
        self.assertEqual([j["status"] for j in rec["journal"]], ["RECEIVED", "PARSED", "ANALYZED", "COMPLETED"])
        answered = {q["questionId"] for q in rec["questions"] if q["answerStatus"] == "ANSWERED"}
        self.assertEqual(answered, {"01-F01", "01-F04", "01-F17", "01-F18"})
        self.assertEqual(len(rec["questions"]), 20)
        self.assertEqual(rec["questions"][0]["questionText"], "Was ist das Ziel?")
        f04 = next(q for q in rec["questions"] if q["questionId"] == "01-F04")
        self.assertEqual((f04["questionText"], f04["text"]), ("Rollen", "Der Dealer darf Aufträge stornieren."))
        self.assertIn("coverage", r.get_json())
        self.assertGreater(rec["counts"]["claims"], 0)

    def test_docx_import_with_tables_and_media(self):
        docx = make_docx([("h", "Kapitel 01"), "01-F01 Ziel", "oneSCM unterstützt den Dealer im Markt Deutschland.",
                          [["Spalte Ä", "Spalte Ö"], ["Wert ü", "Wert ß"]], "F02", "Der Nutzen ist eine schnellere Abwicklung."],
                         media={"image1.png": b"\x89PNG\r\n\x1a\nfake"})
        r = self.upload(docx, "kapitel.docx")
        self.assertEqual(r.status_code, 201, r.get_json())
        rec = r.get_json()["importRecord"]
        table = rec["tables"][0]
        self.assertEqual(table["tableId"], "TBL-CH01-001")
        self.assertEqual(table["header"], ["Spalte Ä", "Spalte Ö"])
        self.assertEqual(table["rows"], [["Wert ü", "Wert ß"]])
        self.assertEqual(table["sourceQuestionId"], "01-F01")
        self.assertEqual(rec["media"][0]["name"], "image1.png")
        self.assertTrue((self.tmp / "data" / "media" / "CH01" / rec["importId"] / "image1.png").exists())

    def test_wrong_type_rejected(self):
        r = self.upload(b"hello", "notes.txt")
        self.assertEqual(r.status_code, 415)
        self.assertIn(".txt", r.get_json()["error"])
        self.assertEqual(r.get_json()["code"], "WRONG_TYPE")

    def test_empty_file_rejected(self):
        r = self.upload(b"", "leer.html")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["code"], "EMPTY")

    def test_corrupt_docx_rejected_and_journalled(self):
        r = self.upload(b"PK\x03\x04 not really a zip", "kaputt.docx")
        self.assertEqual(r.status_code, 422)
        self.assertIn("beschädigt", r.get_json()["error"])
        self.upload(CH01_HTML, "ok.html")  # recomputes the chapter gate
        failed = next(i for i in self.client.get("/api/imports").get_json() if i["file"] == "kaputt.docx")
        self.assertEqual((failed["status"], failed["gate"]), ("FAILED", "BLOCKED"))
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as z:
            z.writestr("other.xml", "<x/>")
        r = self.upload(buffer.getvalue(), "ohne_document.docx")
        self.assertEqual(r.status_code, 422)
        self.assertIn("document.xml", r.get_json()["error"])

    def test_too_large_rejected(self):
        r = self.upload(b"<p>" + b"x" * (50 * 1024 * 1024) + b"</p>", "gross.html")
        self.assertEqual(r.status_code, 413)
        self.assertIn("50 MB", r.get_json()["error"])

    def test_no_content_and_no_questions(self):
        r = self.upload(html_doc(), "leer.html")
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.get_json()["code"], "NO_CONTENT")
        r = self.upload(html_doc(p("Nur Text ohne Fragekennung.")), "ohne.html")
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.get_json()["code"], "NO_QUESTIONS")

    def test_tolerant_question_ids(self):
        doc = html_doc(p("F01 Antwort eins ist hier."), p("01 F02 Antwort zwei ist hier."), p("01-F03: Antwort drei ist hier."),
                       p("CH01-F04 Antwort vier ist hier."), p("f5: Antwort fünf ist hier."), p("01_F06 Antwort sechs ist hier."),
                       p("F21 ungültig ist hier."))
        rec = self.upload(doc, "ids.html").get_json()["importRecord"]
        answered = [q["questionId"] for q in rec["questions"] if q["answerStatus"] == "ANSWERED"]
        self.assertEqual(answered, ["01-F01", "01-F02", "01-F03", "01-F04", "01-F05", "01-F06"])
        self.assertTrue(any("F21" in w for w in rec["warnings"]))

    def test_chapter_mismatch_blocks(self):
        doc = html_doc(p("01-F01 Gültige Antwort für Kapitel eins."), p("02-F01 Antwort aus Kapitel zwei."))
        r = self.upload(doc, "mismatch.html")
        rec = r.get_json()["importRecord"]
        self.assertEqual(rec["validationStatus"], "BLOCKED")
        self.assertEqual(rec["errors"][0]["code"], "CHAPTER_MISMATCH")
        self.assertEqual(r.get_json()["coverage"]["gate"], "BLOCKED")

    def test_all_chapters_selectable(self):
        chapters = self.client.get("/api/meta").get_json()["chapters"]
        self.assertEqual([c["chapterId"] for c in chapters], [f"CH{i:02d}" for i in range(1, 17)])
        self.assertEqual(chapters[0]["schemaStatus"], "REFERENCE")
        ch12 = self.client.get("/api/chapters/CH12").get_json()
        self.assertEqual(ch12["questions"][0]["questionId"], "12-F01")
        self.assertEqual(ch12["questions"][-1]["questionId"], "12-F20")
        r = self.upload(html_doc(p("12-F03 Templates werden vom Dealer erstellt.")), "ch12.html", chapter="CH12")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.client.get("/api/chapters/CH17").status_code, 400)
        self.assertEqual(self.upload(CH01_HTML, "x.html", chapter="CH00").status_code, 400)

    def test_language_validation(self):
        self.assertEqual(self.upload(CH01_HTML, "x.html", language="FR").status_code, 400)
        self.assertEqual(self.upload(CH01_HTML, "x.html", language="DE+EN").status_code, 201)

    def test_idempotent_reimport_and_force(self):
        first = self.upload(CH01_HTML, "ch01.html").get_json()["importRecord"]
        claims_before = len(self.client.get("/api/claims").get_json())
        second = self.upload(CH01_HTML, "ch01.html")
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.get_json()["importRecord"]["duplicate"])
        self.assertEqual(second.get_json()["importRecord"]["importId"], first["importId"])
        self.assertEqual(len(self.client.get("/api/claims").get_json()), claims_before)
        forced = self.upload(CH01_HTML, "ch01.html", force=True).get_json()["importRecord"]
        self.assertEqual(forced["importId"], first["importId"])
        self.assertIn("REPROCESSED", [j["status"] for j in forced["journal"]])
        self.assertEqual(len(self.client.get("/api/claims").get_json()), claims_before)
        self.assertEqual(len(self.client.get("/api/imports").get_json()), 1)

    def test_filename_sanitized(self):
        rec = self.upload(CH01_HTML, "..\\..\\evil<script>.html").get_json()["importRecord"]
        self.assertNotIn("..", rec["sourceFile"]["name"])
        self.assertNotIn("<", rec["sourceFile"]["name"])
        self.assertTrue(rec["sourceFile"]["name"].endswith(".html"))
        raw = list((self.tmp / "data" / "raw").iterdir())
        self.assertEqual(len(raw), 1)
        self.assertEqual(raw[0].parent, self.tmp / "data" / "raw")

    def test_delete_and_archive_import(self):
        rec = self.upload(CH01_HTML, "ch01.html").get_json()["importRecord"]
        self.assertEqual(self.post(f"/api/imports/{rec['importId']}/archive", {}).status_code, 409)
        self.assertEqual(self.post(f"/api/imports/{rec['importId']}/archive", {"force": True}).status_code, 200)
        self.assertEqual(self.client.get("/api/imports").get_json(), [])
        self.assertTrue((self.tmp / "data" / "archive" / rec["importId"] / f"{rec['importId']}.json").exists())
        rec2 = self.upload(html_doc(p("F01 Eine andere Antwort mit Inhalt.")), "b.html").get_json()["importRecord"]
        self.assertTrue(self.client.get("/api/claims").get_json())
        self.assertEqual(self.delete(f"/api/imports/{rec2['importId']}").status_code, 200)
        self.assertEqual([c for c in self.client.get("/api/claims").get_json() if c["sourceImportId"] == rec2["importId"]], [])


class TableTests(AppCase, unittest.TestCase):
    def test_tables_ids_header_position_uneven(self):
        rec = self.upload(CH01_HTML, "ch01.html").get_json()["importRecord"]
        before, roles = rec["tables"]
        self.assertEqual(before["tableId"], "TBL-CH01-001")
        self.assertIsNone(before["sourceQuestionId"])
        self.assertTrue(before["reviewRequired"])
        self.assertEqual(roles["tableId"], "TBL-CH01-002")
        self.assertEqual(roles["sourceQuestionId"], "01-F04")
        self.assertEqual(roles["header"], ["Rolle", "Recht", "Größe"])
        self.assertTrue(roles["unevenRows"])
        self.assertEqual(rec["validationStatus"], "WARNINGS")
        # Next import continues the chapter-wide numbering.
        rec2 = self.upload(html_doc(p("F02 Nutzen."), html_table([["a", "b"], ["1", "2"]])), "t2.html").get_json()["importRecord"]
        self.assertEqual(rec2["tables"][0]["tableId"], "TBL-CH01-003")

    def test_table_export_and_assignment(self):
        self.upload(CH01_HTML, "ch01.html")
        csv = self.client.get("/api/tables/TBL-CH01-002.csv")
        self.assertEqual(csv.status_code, 200)
        self.assertTrue(csv.data.startswith(b"\xef\xbb\xbf"))
        text = csv.data.decode("utf-8-sig")
        self.assertEqual(text.splitlines()[0], "Rolle;Recht;Größe")
        self.assertEqual(text.splitlines()[2], "Market Operations;Genehmigen;")
        data = json.loads(self.client.get("/api/tables/TBL-CH01-002.json").data)
        self.assertEqual(data["tableId"], "TBL-CH01-002")
        r = self.put("/api/tables/TBL-CH01-001", {"sourceQuestionId": "01-F01", "reviewed": True})
        self.assertEqual(r.get_json()["sourceQuestionId"], "01-F01")
        self.assertFalse(r.get_json()["reviewRequired"])
        self.assertEqual(self.put("/api/tables/TBL-CH01-001", {"sourceQuestionId": "02-F01"}).status_code, 400)
        self.assertEqual(self.client.get("/api/tables/TBL-CH01-999.csv").status_code, 404)

    def test_html_nested_table_and_scripts_ignored(self):
        doc = html_doc("<script>01-F05 nicht zählen</script>", p("F01 Antwort steht hier."),
                       "<table><tr><th>A</th><th>B</th></tr><tr><td>x<table><tr><td>inner</td></tr></table></td><td>y</td></tr></table>")
        rec = self.upload(doc, "nested.html").get_json()["importRecord"]
        self.assertEqual(len(rec["tables"]), 1)
        self.assertEqual(rec["tables"][0]["rows"], [["x inner", "y"]])
        self.assertEqual([q["questionId"] for q in rec["questions"] if q["answerStatus"] == "ANSWERED"], ["01-F01"])

    def test_cp1252_html(self):
        doc = "<html><head><meta charset='windows-1252'></head><body><p>F01 Größe und Übersicht für Händler.</p></body></html>".encode("cp1252")
        rec = self.upload(doc, "alt.htm").get_json()["importRecord"]
        self.assertIn("Größe", rec["questions"][0]["text"])
        self.assertTrue(re.search("Händler", rec["questions"][0]["text"]))


if __name__ == "__main__":
    unittest.main()
