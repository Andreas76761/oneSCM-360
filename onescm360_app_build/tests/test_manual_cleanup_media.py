import json
import os
import time
import unittest
from datetime import datetime, timedelta, timezone

from helpers import CH01_HTML, ROOT, AppCase, html_doc, make_docx, p
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
        self.assertEqual(len(files), 2)
        self.assertTrue(all(f.startswith("05_Manual_Generated/Draft/CH01_") for f in files))
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


if __name__ == "__main__":
    unittest.main()
