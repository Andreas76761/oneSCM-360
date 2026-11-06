import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import CH01_HTML, ROOT, AppCase, H, html_doc, p
from app import create_app


class ChapterEditorTests(AppCase, unittest.TestCase):
    def chapter(self, cid="CH05"):
        return self.client.get(f"/api/chapters/{cid}").get_json()

    def edited(self, **changes):
        cfg = self.chapter()
        cfg.update(changes)
        return cfg

    def test_save_goes_to_data_not_program_folder(self):
        shipped = (ROOT / "chapters" / "CH05.json").read_bytes()
        self.assertFalse(self.chapter()["customized"])
        cfg = self.edited(title="Vertragsverwaltung", schemaStatus="REFERENCE", roles=["Dealer", "HQ"],
                          mandatoryEvaluations=["Vertragsmatrix", "RACI"])
        cfg["questions"][0].update(title="Welche Vertragsarten gibt es?", group="Verträge", criticality="CRITICAL", titleEn="Which contract types exist?")
        r = self.put("/api/chapters/CH05", cfg)
        self.assertEqual(r.status_code, 200, r.get_json())
        saved = r.get_json()
        self.assertTrue(saved["customized"])
        self.assertEqual((saved["title"], saved["schemaStatus"], saved["roles"]), ("Vertragsverwaltung", "REFERENCE", ["Dealer", "HQ"]))
        self.assertEqual(saved["questions"][0]["criticality"], "CRITICAL")
        self.assertTrue((self.tmp / "data" / "chapters" / "CH05.json").exists())
        self.assertEqual((ROOT / "chapters" / "CH05.json").read_bytes(), shipped)  # program folder untouched
        meta = next(c for c in self.client.get("/api/meta").get_json()["chapters"] if c["chapterId"] == "CH05")
        self.assertEqual((meta["title"], meta["customized"]), ("Vertragsverwaltung", True))

    def test_validation(self):
        cfg = self.chapter()
        self.assertEqual(self.put("/api/chapters/CH05", {**cfg, "questions": cfg["questions"][:19]}).status_code, 400)
        swapped = cfg["questions"][:]
        swapped[0], swapped[1] = swapped[1], swapped[0]
        self.assertEqual(self.put("/api/chapters/CH05", {**cfg, "questions": swapped}).status_code, 400)
        self.assertEqual(self.put("/api/chapters/CH05", {**cfg, "title": "  "}).status_code, 400)
        self.assertEqual(self.put("/api/chapters/CH05", {**cfg, "roles": ["Chef"]}).status_code, 400)
        self.assertEqual(self.put("/api/chapters/CH05", {**cfg, "schemaStatus": "FINAL"}).status_code, 400)
        bad = json.loads(json.dumps(cfg))
        bad["questions"][3]["criticality"] = "URGENT"
        self.assertEqual(self.put("/api/chapters/CH05", bad).status_code, 400)
        empty = json.loads(json.dumps(cfg))
        empty["questions"][3]["title"] = ""
        self.assertEqual(self.put("/api/chapters/CH05", empty).status_code, 400)
        self.assertEqual(self.put("/api/chapters/CH17", cfg).status_code, 400)
        self.assertFalse((self.tmp / "data" / "chapters" / "CH05.json").exists())

    def test_criticality_drives_coverage(self):
        self.upload(html_doc(p("05-F01 Der Dealer legt Verträge im Portal an.")), "ch05.html", chapter="CH05")
        self.assertEqual(self.client.get("/api/coverage/CH05").get_json()["blockers"], [])
        cfg = self.chapter()
        cfg["questions"][0]["criticality"] = "CRITICAL"
        self.put("/api/chapters/CH05", cfg)
        cov = self.client.get("/api/coverage/CH05").get_json()
        self.assertEqual(cov["gate"], "BLOCKED")
        self.assertTrue(any("Kritischer Claim ohne direkte Evidence" in b for b in cov["blockers"]))

    def test_reset_and_backup(self):
        self.put("/api/chapters/CH05", self.edited(title="Erster Stand"))
        self.put("/api/chapters/CH05", self.edited(title="Zweiter Stand"))
        self.assertTrue(list((self.tmp / "data" / "backups").glob("chapter-CH05-*.json")))
        restored = self.delete("/api/chapters/CH05/override").get_json()
        self.assertFalse(restored["customized"])
        self.assertEqual(restored["title"], "Kapitel 05")
        self.assertEqual(self.delete("/api/chapters/CH05/override").status_code, 400)

    def test_csv_roundtrip_and_parsing(self):
        csv = self.client.get("/api/chapters/CH05/questions.csv")
        self.assertTrue(csv.data.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(csv.data.decode("utf-8-sig").splitlines()[0], "QuestionId;Gruppe;Titel;TitleEN;Kritikalitaet")
        content = ("Frage;Gruppe;Titel;Kritikalität\r\n05-F01;Verträge;Welche Vertragsarten gibt es?;kritisch\r\n"
                   "F02;Verträge;Wer darf Verträge ändern?;hoch\r\n").encode("cp1252")
        r = self.client.post("/api/chapters/CH05/questions.csv", data={"file": (io.BytesIO(content), "katalog.csv")},
                             headers=H, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200, r.get_json())
        questions = r.get_json()["questions"]
        self.assertEqual(len(questions), 20)
        self.assertEqual((questions[0]["title"], questions[0]["criticality"], questions[0]["group"]),
                         ("Welche Vertragsarten gibt es?", "CRITICAL", "Verträge"))
        self.assertEqual((questions[1]["title"], questions[1]["criticality"]), ("Wer darf Verträge ändern?", "HIGH"))
        self.assertEqual(questions[2]["title"], "Frage 05-F03")  # untouched rows keep their values
        self.assertFalse((self.tmp / "data" / "chapters" / "CH05.json").exists())  # parsing never saves
        for bad in (b"Frage;Gruppe\r\nF01;x\r\n", b"Frage;Titel\r\nF21;x\r\n", b"Frage;Titel;Kritikalitaet\r\nF01;x;sofort\r\n", b""):
            r = self.client.post("/api/chapters/CH05/questions.csv", data={"file": (io.BytesIO(bad), "x.csv")}, headers=H,
                                 content_type="multipart/form-data")
            self.assertEqual(r.status_code, 400, bad)


class RulesLocationTests(unittest.TestCase):
    def test_rule_set_is_kept_in_data_folder(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            shipped = (ROOT / "rules.json").read_bytes()
            app = create_app({"DATA_DIR": tmp / "data", "ONEDRIVE_ROOT": str(tmp)})
            client = app.test_client()
            self.assertTrue((tmp / "data" / "rules.json").exists())
            r = client.post("/api/rules", json={"category": "system", "source": "SAP"}, headers=H)
            self.assertEqual(r.status_code, 201)
            self.assertIn("SAP", (tmp / "data" / "rules.json").read_text(encoding="utf-8"))
            self.assertEqual((ROOT / "rules.json").read_bytes(), shipped)  # program folder untouched
            again = create_app({"DATA_DIR": tmp / "data", "ONEDRIVE_ROOT": str(tmp)}).test_client()
            self.assertIn("SAP", [x["source"] for x in again.get("/api/rules").get_json()])  # edits survive a restart
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class KnowledgeBlockStatusTests(AppCase, unittest.TestCase):
    def blocks(self):
        return {b["questionId"]: b for b in self.client.get("/api/knowledge-blocks?chapterId=CH01").get_json()}

    def test_status_and_version_follow_claims(self):
        self.upload(CH01_HTML, "ch01.html")
        block = self.blocks()["01-F04"]
        self.assertEqual((block["validationStatus"], block["version"]), ("DRAFT", 1))
        claim = next(c for c in self.client.get("/api/claims?questionId=01-F04").get_json())
        self.put(f"/api/claims/{claim['claimId']}", {"validationStatus": "REVIEWED"})
        self.assertEqual((self.blocks()["01-F04"]["validationStatus"], self.blocks()["01-F04"]["version"]), ("REVIEWED", 2))
        self.put(f"/api/claims/{claim['claimId']}", {"validationStatus": "CONFIRMED"})
        self.assertEqual(self.blocks()["01-F04"]["validationStatus"], "CONFIRMED")
        self.post("/api/sync/export", {"chapterId": "CH01"})
        kb_csv = next(self.onedrive.rglob("*_KnowledgeBlocks.csv")).read_bytes().decode("utf-8-sig")
        row = next(line for line in kb_csv.splitlines() if ";01-F04;" in line)
        self.assertIn(";CONFIRMED;3;", row)
        self.put(f"/api/claims/{claim['claimId']}", {"validationStatus": "REJECTED"})
        self.assertEqual(self.blocks()["01-F04"]["validationStatus"], "REJECTED")
        self.delete(f"/api/claims/{claim['claimId']}")
        self.assertEqual(self.blocks()["01-F04"]["validationStatus"], "DRAFT")  # no claims left


if __name__ == "__main__":
    unittest.main()
