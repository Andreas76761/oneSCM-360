import html
import io
import json
import os
import time
import zipfile
import unittest
from datetime import datetime, timedelta, timezone

from helpers import CH01_HTML, ROOT, AppCase, H, html_doc, make_docx, p
from services.design_service import validate
from services.manual_service import build_manual, stage_allowed


class ManualTests(AppCase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.upload(CH01_HTML, "ch01.html")

    def test_stage_rules(self):
        self.assertEqual(stage_allowed("Draft", "BLOCKED"), (True, ""))
        self.assertFalse(stage_allowed("Reviewed", "BLOCKED")[0])
        self.assertTrue(stage_allowed("Reviewed", "INCOMPLETE")[0])
        self.assertFalse(stage_allowed("Released", "REVIEW")[0])
        self.assertTrue(stage_allowed("Released", "READY")[0])
        self.assertFalse(stage_allowed("Final", "READY")[0])

    def test_draft_preview_content_and_escaping(self):
        self.post("/api/claims", {"chapterId": "CH01", "questionId": "01-F13", "canonicalStatement": "Der Report <script>alert(1)</script> wird erzeugt."})
        r = self.client.get("/api/manual/CH01/preview?stage=Draft")
        self.assertEqual(r.status_code, 200)
        self.assertIn("default-src 'none'", r.headers["Content-Security-Policy"])
        page = r.get_data(as_text=True)
        self.assertIn("<title>oneSCM Benutzerhandbuch – CH01 Grundlagen und Überblick</title>", page)
        self.assertIn("Kapitel 01 – Grundlagen und Überblick", page)
        self.assertIn('<span class="badge b-open">Offen</span>', page)  # unreviewed statement badge
        self.assertIn('<span class="badge b-both">beide</span>', page)  # PC and VAN
        self.assertIn("Der Dealer darf Aufträge stornieren.", page)
        self.assertIn("ungeprüft", page)
        self.assertIn("TBL-CH01-002", page)  # table assigned to 01-F04
        self.assertNotIn("TBL-CH01-001", page)  # unassigned table needs review first
        self.assertIn("Program Increment", page)  # glossary from the rule set
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)

    def test_stage_gates_via_api(self):
        self.assertEqual(self.client.get("/api/manual/CH01/preview?stage=Reviewed").status_code, 409)  # CH01 is BLOCKED
        self.assertIn("READY", self.client.get("/api/manual/CH01/preview?stage=Released").get_json()["error"])
        self.assertEqual(self.client.get("/api/manual/CH01/preview?stage=Final").status_code, 400)
        self.assertEqual(self.client.get("/api/manual/CH99/preview").status_code, 400)

    def test_released_contains_only_confirmed(self):
        chapter = json.loads((ROOT / "chapters" / "CH01.json").read_text(encoding="utf-8"))
        claims = [{"claimId": "C1", "chapterId": "CH01", "questionId": "01-F01", "canonicalStatement": "Freigegebene Aussage.", "validationStatus": "CONFIRMED"},
                  {"claimId": "C2", "chapterId": "CH01", "questionId": "01-F01", "canonicalStatement": "Geprüfte Aussage.", "validationStatus": "REVIEWED"},
                  {"claimId": "C3", "chapterId": "CH01", "questionId": "01-F02", "canonicalStatement": "Abgelehnt.", "validationStatus": "REJECTED"}]
        evidence = [{"claimId": "C1", "sourceType": "JIRA", "jiraKey": "ONESCM-7", "evidenceStrength": "DIRECT_VALIDATED", "evidenceStatus": "VALIDATED"}]
        coverage = {"gate": "READY", "readiness": 95.0}
        design = validate(json.loads((ROOT / "design_templates.json").read_text(encoding="utf-8"))["templates"][0])
        manual = build_manual(chapter, "Released", claims, evidence, [], coverage, [], [], design)
        self.assertIn("Freigegebene Aussage.", manual["html"])
        self.assertIn("ONESCM-7", manual["html"])
        self.assertNotIn("Geprüfte Aussage.", manual["html"])
        self.assertNotIn("Abgelehnt.", manual["html"])
        self.assertNotIn("Kein freigegebener Handbuchstand", manual["html"])
        self.assertEqual(manual["stats"]["claims"], 1)
        reviewed = build_manual(chapter, "Reviewed", claims, evidence, [], coverage, [], [], design)
        self.assertIn("Geprüfte Aussage.", reviewed["html"])
        self.assertIn("- Geprüfte Aussage. _(geprüft)_", reviewed["markdown"])

    def test_generate_writes_to_onedrive(self):
        r = self.post("/api/manual/CH01", {"stage": "Draft"})
        self.assertEqual(r.status_code, 201, r.get_json())
        files = r.get_json()["files"]
        self.assertEqual([f.rsplit(".", 1)[1] for f in files], ["html", "docx", "md"])
        self.assertTrue(all(f.startswith("05_Manual_Generated/Draft/CH01_") for f in files))
        self.assertEqual((self.onedrive / files[1]).read_bytes()[:2], b"PK")
        self.assertTrue((self.onedrive / files[0]).read_text(encoding="utf-8").startswith("<!doctype html>"))
        second = self.post("/api/manual/CH01", {"stage": "Draft"}).get_json()["files"]
        self.assertNotEqual(files, second)  # never overwrite
        self.post("/api/sync/settings", {"onedriveRoot": str(self.tmp / "fehlt")})
        self.assertEqual(self.post("/api/manual/CH01", {"stage": "Draft"}).status_code, 409)


class CleanupTests(AppCase, unittest.TestCase):
    def preview(self):
        return self.client.get("/api/cleanup/preview").get_json()

    def age(self, import_id, days):
        path = self.tmp / "data" / "imports" / f"{import_id}.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["createdAt"] = (datetime.now(timezone.utc) - timedelta(days=days)).replace(microsecond=0).isoformat()
        path.write_text(json.dumps(record), encoding="utf-8")

    def test_rules_preview_and_execute(self):
        exported = self.upload(CH01_HTML, "exportiert.html").get_json()["importRecord"]
        self.post("/api/sync/export", {"chapterId": "CH01"})
        fresh = self.upload(html_doc(p("F02 Der Nutzen ist eine schnellere Abwicklung.")), "neu.html").get_json()["importRecord"]
        self.upload(html_doc(p("Kein Fragenformat.")), "kaputt.html")
        failed = next(r for r in self.client.get("/api/imports").get_json() if r["status"] == "FAILED")
        (self.tmp / "data" / "imports" / "IMP-20260101-000000-ABCDEF.json").write_text("{x", encoding="utf-8")
        self.assertEqual([i["target"] for i in self.preview()["items"]], ["IMP-20260101-000000-ABCDEF"])  # only the broken JSON yet
        self.age(exported["importId"], 40)
        self.age(fresh["importId"], 40)  # old but never exported → kept
        self.age(failed["importId"], 20)
        items = {i["target"]: i["action"] for i in self.preview()["items"]}
        self.assertEqual(items, {"IMP-20260101-000000-ABCDEF": "quarantine", failed["importId"]: "delete", exported["importId"]: "archive"})
        claims_before = len(self.client.get("/api/claims").get_json())
        self.assertEqual(self.post("/api/cleanup", {"targets": list(items)}).status_code, 400)  # confirmation required
        r = self.post("/api/cleanup", {"targets": list(items) + ["IMP-NOT-IN-PREVIEW"], "confirm": True}).get_json()
        self.assertEqual(len(r["done"]), 3)
        self.assertEqual(r["skipped"][0]["target"], "IMP-NOT-IN-PREVIEW")
        remaining = [row["importId"] for row in self.client.get("/api/imports").get_json()]
        self.assertEqual(remaining, [fresh["importId"]])
        self.assertTrue((self.tmp / "data" / "archive" / "_invalid" / "IMP-20260101-000000-ABCDEF.json").exists())
        self.assertTrue((self.tmp / "data" / "archive" / exported["importId"]).is_dir())
        self.assertEqual(len(self.client.get("/api/claims").get_json()), claims_before)  # archiving keeps knowledge

    def test_purge_old_archive(self):
        rec = self.upload(CH01_HTML, "a.html").get_json()["importRecord"]
        self.post(f"/api/imports/{rec['importId']}/archive", {"force": True})
        folder = self.tmp / "data" / "archive" / rec["importId"]
        self.assertEqual(self.preview()["items"], [])
        old = time.time() - 400 * 86400
        os.utime(folder, (old, old))
        items = self.preview()["items"]
        self.assertEqual((items[0]["action"], items[0]["target"]), ("purge", rec["importId"]))
        self.post("/api/cleanup", {"targets": [rec["importId"]], "confirm": True})
        self.assertFalse(folder.exists())


class MediaTests(AppCase, unittest.TestCase):
    def test_media_served_safely(self):
        docx = make_docx(["01-F01 Der Dealer sieht die Übersicht."], media={"image1.png": b"\x89PNG\r\n\x1a\nfake", "image2.emf": b"EMF"})
        rec = self.upload(docx, "bild.docx").get_json()["importRecord"]
        r = self.client.get(f"/api/media/{rec['importId']}/image1.png")
        self.assertEqual((r.status_code, r.mimetype), (200, "image/png"))
        self.assertTrue(r.data.startswith(b"\x89PNG"))
        r.close()
        emf = self.client.get(f"/api/media/{rec['importId']}/image2.emf")
        self.assertIn("attachment", emf.headers["Content-Disposition"])
        emf.close()
        self.assertEqual(self.client.get(f"/api/media/{rec['importId']}/image9.png").status_code, 404)
        self.assertEqual(self.client.get(f"/api/media/{rec['importId']}/..%2F..%2Fknowledge.json").status_code, 404)
        self.assertEqual(self.client.get("/api/media/IMP-20260101-000000-ABCDEF/image1.png").status_code, 404)


def png(width: int, height: int) -> bytes:
    """A real PNG of the given size (one colour), so header parsing and rendering can be checked."""
    import struct
    import zlib

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\x00\x70\x8a" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class ManualImageTests(AppCase, unittest.TestCase):
    def import_with_images(self, name="bilder.docx", note="Stand A"):
        docx = make_docx([note, ("img", "image9.png", "Logo vor der ersten Frage"),
                          "01-F01 Ziel", "oneSCM unterstützt den Dealer bei Aufträgen.", ("img", "image1.png", "Übersichtsmaske"),
                          "01-F04 Rollen", "Der Dealer darf Aufträge stornieren.", ("img", "image2.emf", ""),
                          [["Rolle", "Recht"], ["Dealer", "Bestellen"]], ("img", "image3.png", "Rollenmatrix")],
                         media={"image1.png": png(800, 450), "image2.emf": b"\x01\x00\x00\x00" + bytes(100),
                                "image3.png": png(40, 20), "image9.png": png(10, 10)})
        return self.upload(docx, name).get_json()["importRecord"]

    def test_classify_preview_with_images(self):
        docx = make_docx(["01-F01 Ziel", "Der Dealer sieht die Übersicht.", ("img", "image1.png", "Maske")], media={"image1.png": png(4, 4)})
        r = self.client.post("/api/import/classify", data={"file": (io.BytesIO(docx), "CH01_Bilder_DE.docx")},
                             headers=H, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        self.assertEqual(r.get_json()["chapterId"], "CH01")

    def test_images_are_assigned_to_their_question(self):
        rec = self.import_with_images()
        media = {m["name"]: m for m in rec["media"]}
        self.assertEqual((media["image1.png"]["questionId"], media["image1.png"]["alt"], media["image1.png"]["inManual"]),
                         ("01-F01", "Übersichtsmaske", True))
        self.assertEqual(media["image2.emf"]["questionId"], "01-F04")
        self.assertEqual(media["image3.png"]["questionId"], "01-F04")
        self.assertEqual((media["image9.png"]["questionId"], media["image9.png"]["inManual"]), (None, False))

    def test_assignment_can_be_changed(self):
        rec = self.import_with_images()
        url = f"/api/media/{rec['importId']}/image9.png"
        self.assertEqual(self.client.patch(url, json={"questionId": "01-F02"}).status_code, 403)  # CSRF header missing
        bad = self.client.patch(url, json={"inManual": True}, headers=H)
        self.assertEqual(bad.status_code, 400)
        self.assertIn("einer Frage zugeordnet", bad.get_json()["error"])
        self.assertEqual(self.client.patch(url, json={"questionId": "01-F99"}, headers=H).status_code, 400)
        item = self.client.patch(url, json={"questionId": "01-F02", "inManual": True, "alt": "Logo"}, headers=H).get_json()
        self.assertEqual((item["questionId"], item["inManual"], item["alt"]), ("01-F02", True, "Logo"))
        self.client.patch(f"/api/media/{rec['importId']}/image3.png", json={"inManual": False}, headers=H)
        stored = {m["name"]: m for m in self.client.get(f"/api/imports/{rec['importId']}").get_json()["media"]}
        self.assertEqual(stored["image9.png"]["questionId"], "01-F02")
        self.assertFalse(stored["image3.png"]["inManual"])
        self.assertEqual(self.client.patch(f"/api/media/{rec['importId']}/fehlt.png", json={}, headers=H).status_code, 404)

    def test_manual_html_and_word_contain_images(self):
        rec = self.import_with_images()
        self.client.patch(f"/api/media/{rec['importId']}/image3.png", json={"inManual": False}, headers=H)
        self.import_with_images("bilder_kopie.docx", "Stand B")  # another file with the same pictures: appear only once
        page = self.client.get("/api/manual/CH01/preview?stage=Draft").get_data(as_text=True)
        self.assertEqual(page.count("data:image/png;base64,"), 1)
        self.assertIn("Abbildung 1.1-1 – Übersichtsmaske", page)
        self.assertIn("EMF-Grafik, nur im Word-Handbuchstand sichtbar", page)
        self.assertNotIn("Rollenmatrix", page)
        r = self.client.get("/api/manual/CH01/docx?stage=Draft")
        with zipfile.ZipFile(io.BytesIO(r.data)) as z:
            names = z.namelist()
            doc = z.read("word/document.xml").decode("utf-8")
            rels = z.read("word/_rels/document.xml.rels").decode("utf-8")
            types = z.read("[Content_Types].xml").decode("utf-8")
            self.assertEqual(z.read("word/media/bild1.png")[:4], b"\x89PNG")
        self.assertEqual(sorted(n for n in names if n.startswith("word/media/")), ["word/media/bild1.png", "word/media/bild2.emf"])
        self.assertIn('r:embed="rIdImg1"', doc)
        self.assertIn('Target="media/bild1.png"', rels)
        self.assertIn('Extension="emf"', types)
        self.assertIn("Abbildung 1.1-1 – Übersichtsmaske", doc)
        self.assertIn('descr="Übersichtsmaske"', doc)
        # 800 × 450 px at 96 dpi is 21.2 cm wide: scaled down to the text width of the A4 template
        import re
        cx, cy = map(int, re.search(r'<wp:extent cx="(\d+)" cy="(\d+)"/>', doc).groups())
        self.assertAlmostEqual(cx / 360000, 16.0, delta=0.05)  # A4 minus margins 2.5 cm each side
        self.assertAlmostEqual(cy / cx, 450 / 800, delta=0.001)
        r = self.post("/api/manual/CH01", {"stage": "Draft"}).get_json()
        self.assertEqual(r["stats"]["images"], 2)

    def test_word_manual_with_images_opens_in_python_docx(self):
        try:
            import docx
        except ImportError:
            self.skipTest("python-docx nicht installiert")
        self.import_with_images()
        document = docx.Document(io.BytesIO(self.client.get("/api/manual/CH01/docx?stage=Draft").data))
        self.assertEqual(len(document.inline_shapes), 3)

    def test_image_size_from_headers(self):
        from services.word_template import image_size
        self.assertEqual(image_size(png(123, 45), "png"), (123, 45))
        self.assertEqual(image_size(b"GIF89a" + (300).to_bytes(2, "little") + (200).to_bytes(2, "little"), "gif"), (300, 200))
        jpeg = b"\xff\xd8\xff\xe0\x00\x04ab\xff\xc0\x00\x11\x08" + (480).to_bytes(2, "big") + (640).to_bytes(2, "big") + bytes(12)
        self.assertEqual(image_size(jpeg, "jpg"), (640, 480))
        self.assertIsNone(image_size(b"kaputt", "png"))


class BookTests(AppCase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.upload(CH01_HTML, "ch01.html")
        self.upload(html_doc(p("02-F01 Der Dealer legt Verträge im Portal an.")), "ch02.html", chapter="CH02")

    def test_overview_lists_every_chapter(self):
        r = self.client.get("/api/book/overview?stage=Draft").get_json()
        self.assertEqual(len(r["overview"]), 16)
        rows = {o["chapterId"]: o for o in r["overview"]}
        self.assertTrue(rows["CH01"]["included"] and rows["CH02"]["included"])
        self.assertEqual((rows["CH03"]["included"], rows["CH03"]["reason"]), (False, "noch kein abgeschlossener Import"))
        self.assertEqual(r["stats"]["chapters"], ["CH01", "CH02"])
        released = self.client.get("/api/book/overview?stage=Released").get_json()
        self.assertIsNone(released["stats"])
        self.assertIn("Kein Kapitel erreicht die Stufe Released", released["error"])
        self.assertIn("Released ist nur bei Gate READY", {o["chapterId"]: o for o in released["overview"]}["CH01"]["reason"])
        self.assertEqual(self.client.get("/api/book/overview?stage=Final").status_code, 400)

    def test_preview_and_word_contain_all_chapters(self):
        page = self.client.get("/api/book/preview?stage=Draft&design=training").get_data(as_text=True)
        self.assertIn('<h1 class="chapter-break">1 Kapitel 01 – Grundlagen und Überblick</h1>', page)
        self.assertIn('<h1 class="chapter-break">2 Kapitel 02', page)
        self.assertIn("<h2>1.1 ", page)
        self.assertIn("<h3>1.1.1 ", page)
        self.assertIn("Der Dealer legt Verträge im Portal an.", page)
        self.assertIn("Kapitelübersicht", page)
        self.assertIn("nein – kein Import", page)
        self.assertIn("Glossar", page)
        r = self.client.get("/api/book/docx?stage=Draft")
        self.assertIn('filename="Gesamthandbuch_Draft.docx"', r.headers["Content-Disposition"])
        with zipfile.ZipFile(io.BytesIO(r.data)) as z:
            doc = z.read("word/document.xml").decode("utf-8")
        self.assertIn("1 Kapitel 01 – Grundlagen und Überblick", doc)
        self.assertIn('<w:pStyle w:val="Heading3"/>', doc)
        self.assertIn(" TOC ", doc)
        self.assertEqual(self.client.get("/api/book/docx?stage=Released").status_code, 409)

    def test_generate_writes_three_files(self):
        r = self.post("/api/book", {"stage": "Draft"})
        self.assertEqual(r.status_code, 201, r.get_json())
        files = r.get_json()["files"]
        self.assertEqual([f.rsplit(".", 1)[1] for f in files], ["html", "docx", "md"])
        self.assertTrue(all(f.startswith("05_Manual_Generated/Draft/Gesamthandbuch_") for f in files))
        markdown = (self.onedrive / files[2]).read_text(encoding="utf-8")
        self.assertIn("# 2 Kapitel 02", markdown)
        self.assertIn("| CH03 |", markdown)


class ReleaseLetterTests(AppCase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.upload(CH01_HTML, "ch01.html")

    def claims(self, chapter="CH01"):
        return [c for c in self.client.get("/api/claims").get_json() if c["chapterId"] == chapter]

    def test_without_snapshot(self):
        self.assertEqual(self.client.get("/api/release/snapshots").get_json(), [])
        self.assertEqual(self.client.get("/api/release/preview?since=CH01_20260101-000000_Handbuch_Draft").status_code, 404)
        self.assertEqual(self.client.get("/api/release/preview?since=../../etc").status_code, 404)

    def test_changes_since_chapter_manual(self):
        files = self.post("/api/manual/CH01", {"stage": "Draft"}).get_json()["files"]
        snapshots = self.client.get("/api/release/snapshots").get_json()
        self.assertEqual(len(snapshots), 1)
        since = snapshots[0]["snapshotId"]
        self.assertEqual(since, files[0].rsplit("/", 1)[1][:-5])
        self.assertEqual((snapshots[0]["kind"], snapshots[0]["chapters"]), ("chapter", ["CH01"]))
        unchanged = self.client.get(f"/api/release/preview?since={since}").get_data(as_text=True)
        self.assertIn("Seit der Basis gibt es keine Änderungen.", unchanged)

        claims = self.claims()
        reworded, promoted, rejected = claims[0], claims[1], claims[2]
        self.put(f"/api/claims/{reworded['claimId']}", {"canonicalStatement": "Neu formulierte Aussage zum Ziel."})
        self.put(f"/api/claims/{promoted['claimId']}", {"validationStatus": "REVIEWED"})
        self.put(f"/api/claims/{rejected['claimId']}", {"validationStatus": "REJECTED"})
        created = self.post("/api/claims", {"chapterId": "CH01", "questionId": "01-F02", "canonicalStatement": "Ganz neue Aussage zum Nutzen."})
        self.assertEqual(created.status_code, 201, created.get_json())

        page = self.client.get(f"/api/release/preview?since={since}").get_data(as_text=True)
        self.assertIn("Änderungen seit CH01 Draft vom", page)
        self.assertIn("NEU</span> Ganz neue Aussage zum Nutzen.", page)
        self.assertIn(f"GEÄNDERT</span> Neu formulierte Aussage zum Ziel. <span class=\"src\">(vorher: {html.escape(reworded['canonicalStatement'])})", page)
        self.assertIn("(ungeprüft → geprüft)", page)
        self.assertIn(f"ENTFALLEN</span> {html.escape(rejected['canonicalStatement'])} <span class=\"src\">(Status jetzt abgelehnt)", page)
        self.assertIn("01-F02 · ", page)
        r = self.post("/api/release", {"since": since})
        self.assertEqual(r.status_code, 201, r.get_json())
        stats = r.get_json()["stats"]
        self.assertEqual((stats["new"], stats["changed"], stats["status"], stats["removed"]), (1, 1, 1, 1))
        self.assertTrue(all("/ReleaseLetter_" in f and "_Aenderungen_Draft." in f for f in r.get_json()["files"]))
        self.assertEqual(len(self.client.get("/api/release/snapshots").get_json()), 1)  # a release letter is no new basis
        named = self.client.get(f"/api/release/preview?since={since}&release=PI17").get_data(as_text=True)
        self.assertIn("oneSCM Release Letter · PI17", named)
        self.assertIn("<tr><td>Release</td><td>PI17</td></tr>", named)
        self.assertEqual(self.client.get(f"/api/release/preview?since={since}&release={'x' * 41}").status_code, 400)
        docx = self.client.get(f"/api/release/docx?since={since}&release=PI17")
        with zipfile.ZipFile(io.BytesIO(docx.data)) as z:
            doc = z.read("word/document.xml").decode("utf-8")
            footer = z.read("word/footer1.xml").decode("utf-8")
        self.assertIn("ENTFALLEN", doc)
        self.assertIn("Ganz neue Aussage zum Nutzen.", doc)
        self.assertIn("Release PI17", footer)
        # compared with Reviewed, the unreviewed statements are not part of the manual
        reviewed = self.client.get(f"/api/release/preview?since={since}&stage=Reviewed").get_data(as_text=True)
        self.assertNotIn("Ganz neue Aussage zum Nutzen.", reviewed)  # new but unreviewed: not in a Reviewed manual
        self.assertIn("Status jetzt ungeprüft", reviewed)

    def test_book_snapshot_includes_later_chapters(self):
        self.post("/api/book", {"stage": "Draft"})
        since = self.client.get("/api/release/snapshots").get_json()[0]["snapshotId"]
        self.assertTrue(since.startswith("Gesamthandbuch_"))
        self.upload(html_doc(p("02-F01 Der Dealer legt Verträge im Portal an.")), "ch02.html", chapter="CH02")
        page = self.client.get(f"/api/release/preview?since={since}").get_data(as_text=True)
        self.assertIn("Kapitel 02", page)
        self.assertIn("NEU</span> Der Dealer legt Verträge im Portal an", page)
        self.assertIn("Änderungen seit Gesamthandbuch Draft vom", page)


if __name__ == "__main__":
    unittest.main()
