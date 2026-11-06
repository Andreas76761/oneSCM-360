import csv
import hashlib
import io
import json
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from helpers import CH01_HTML, AppCase
from services.export_service import to_csv


class ExportTests(AppCase, unittest.TestCase):
    def test_status_ready_and_cloud_never_faked(self):
        status = self.client.get("/api/sync/status").get_json()
        self.assertEqual(status["localStatus"], "READY_FOR_CLIENT")
        self.assertTrue(status["exists"] and status["writable"])
        self.assertEqual(status["cloudStatus"], "NOT_VERIFIABLE_WITHOUT_GRAPH")
        self.assertEqual(list(self.onedrive.iterdir()), [])  # write probe removed

    def test_path_missing_and_settings(self):
        r = self.post("/api/sync/settings", {"onedriveRoot": str(self.tmp / "gibt-es-nicht")})
        self.assertEqual(r.get_json()["localStatus"], "PATH_MISSING")
        self.upload(CH01_HTML, "ch01.html")
        self.assertEqual(self.post("/api/sync/export", {"chapterId": "CH01"}).status_code, 409)
        self.assertEqual(self.post("/api/sync/structure", {}).status_code, 409)
        self.assertEqual(self.post("/api/sync/settings", {"onedriveRoot": "relativ\\pfad"}).status_code, 400)
        r = self.post("/api/sync/settings", {"onedriveRoot": ""})
        self.assertEqual(r.get_json()["configuredBy"], "ONESCM_LOCAL_ONEDRIVE_ROOT")
        self.assertEqual(r.get_json()["localStatus"], "READY_FOR_CLIENT")

    def test_not_ready_when_write_test_fails(self):
        exporter = self.services()["exporter"]
        with mock.patch.object(Path, "write_bytes", side_effect=PermissionError(13, "Zugriff verweigert")):
            status = exporter.status()
        self.assertEqual(status["localStatus"], "NOT_READY")
        self.assertIn("Schreibtest", status["reason"])

    def test_unconfigured(self):
        from app import create_app
        app = create_app({"DATA_DIR": self.tmp / "d2", "RULES_PATH": self.rules_path, "ONEDRIVE_ROOT": ""})
        status = app.test_client().get("/api/sync/status").get_json()
        self.assertEqual(status["localStatus"], "PATH_MISSING")
        self.assertEqual(status["path"], "")

    def test_export_files_manifest_zip(self):
        self.assertEqual(self.post("/api/sync/export", {"chapterId": "CH01"}).status_code, 409)  # nothing imported
        rec = self.upload(CH01_HTML, "ch01.html").get_json()["importRecord"]
        r = self.post("/api/sync/export", {"chapterId": "CH01"})
        self.assertEqual(r.status_code, 201, r.get_json())
        result = r.get_json()
        self.assertEqual(result["cloudStatus"], "NOT_VERIFIABLE_WITHOUT_GRAPH")
        for folder in ("01_Rovo_Imports/CH16", "02_Jira_Imports", "04_Source_Documents/Word", "05_Manual_Generated/Released", "99_Archive", "Skill", "Goal"):
            self.assertTrue((self.onedrive / folder).is_dir(), folder)
        files = result["files"]
        self.assertTrue(any(f.startswith("01_Rovo_Imports/CH01/") and f.endswith("ch01.html") for f in files))
        names = {Path(f).name.split("_", 2)[-1] for f in files}
        for expected in ("export.json", "KnowledgeBlocks.csv", "Claims.csv", "Evidence.csv", "Coverage.csv", "TBL-CH01-001.csv", "TBL-CH01-002.json", "confirmed.json"):
            self.assertIn(expected, names)
        kb_csv = next(self.onedrive / f for f in files if f.endswith("KnowledgeBlocks.csv"))
        raw = kb_csv.read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(rows[0][:3], ["KnowledgeId", "ChapterId", "QuestionId"])
        self.assertGreater(len(rows), 1)
        claims_csv = next(self.onedrive / f for f in files if f.endswith("Claims.csv"))
        header = claims_csv.read_bytes().decode("utf-8-sig").splitlines()[0].split(";")
        self.assertIn("CanonicalStatement", header)
        self.assertIn("PI", header)
        manifest = json.loads((self.onedrive / result["manifest"]).read_text(encoding="utf-8"))
        self.assertEqual(manifest["cloudStatus"], "NOT_VERIFIABLE_WITHOUT_GRAPH")
        for entry in manifest["files"]:
            self.assertEqual(hashlib.sha256((self.onedrive / entry["path"]).read_bytes()).hexdigest(), entry["sha256"])
        with zipfile.ZipFile(self.onedrive / result["package"]) as archive:
            members = archive.namelist()
        self.assertTrue(any(m.endswith("Claims.csv") for m in members))
        self.assertTrue(any(m.endswith("_manifest.json") for m in members))
        self.assertFalse(any(m.startswith("01_Rovo_Imports") for m in members))
        # exported imports can be archived without force
        self.assertEqual(self.post(f"/api/imports/{rec['importId']}/archive", {}).status_code, 200)

    def test_exports_in_the_same_second_do_not_overwrite(self):
        from unittest import mock
        from datetime import datetime, timezone
        import services.export_service as es
        self.upload(CH01_HTML, "ch01.html")
        fixed = datetime(2026, 11, 6, 12, 0, 0, tzinfo=timezone.utc)
        with mock.patch.object(es, "datetime") as fake:
            fake.now.return_value = fixed
            fake.fromtimestamp.side_effect = datetime.fromtimestamp
            first = self.post("/api/sync/export", {"chapterId": "CH01"}).get_json()
            second = self.post("/api/sync/export", {"chapterId": "CH01"}).get_json()
        self.assertNotEqual(first["manifest"], second["manifest"])
        self.assertTrue(second["manifest"].endswith("-2_manifest.json"))
        self.assertEqual(len(list(self.onedrive.rglob("*_Claims.csv"))), 2)

    def test_csv_formula_injection_neutralised(self):
        text = to_csv(["A", "B"], [{"A": "=HYPERLINK(\"x\")", "B": "-5"}]).decode("utf-8-sig")
        self.assertIn("'=HYPERLINK", text)
        self.assertIn(";-5", text)


class DashboardTests(AppCase, unittest.TestCase):
    def test_kpis_imports_outputs_refresh(self):
        empty = self.client.get("/api/dashboard").get_json()
        self.assertEqual(empty["kpis"], {"imports": 0, "sourceFiles": 0, "outputFiles": 0, "json": 0, "csv": 0, "packages": 0})
        self.upload(CH01_HTML, "ch01.html")
        self.post("/api/sync/export", {"chapterId": "CH01"})
        data = self.client.get("/api/dashboard").get_json()
        self.assertEqual(data["kpis"]["imports"], 1)
        self.assertEqual(data["kpis"]["sourceFiles"], 1)
        self.assertEqual(data["kpis"]["packages"], 1)
        self.assertGreaterEqual(data["kpis"]["csv"], 5)
        self.assertEqual(data["kpis"]["outputFiles"], len(data["outputs"]))
        row = data["imports"][0]
        self.assertEqual((row["chapterId"], row["file"], row["status"], row["questions"], row["tables"]), ("CH01", "ch01.html", "COMPLETED", 4, 2))
        output = data["outputs"][0]
        self.assertTrue({"name", "path", "size", "modifiedAt"} <= set(output))
        self.assertTrue(data["onedrive"]["lastLocalChange"])

    def test_invalid_json_visible_and_blocking(self):
        self.upload(CH01_HTML, "ch01.html")
        (self.tmp / "data" / "imports" / "IMP-20260101-000000-ABCDEF.json").write_text("{nicht json", encoding="utf-8")
        rows = self.client.get("/api/dashboard").get_json()["imports"]
        broken = next(r for r in rows if r["importId"] == "IMP-20260101-000000-ABCDEF")
        self.assertEqual((broken["status"], broken["gate"]), ("INVALID_JSON", "BLOCKED"))
        cov = self.client.get("/api/coverage/CH02").get_json()
        self.assertEqual(cov["gate"], "BLOCKED")
        self.assertTrue(any("INVALID_JSON" in b for b in cov["blockers"]))
        self.assertEqual(self.client.get("/api/imports/IMP-20260101-000000-ABCDEF").status_code, 500)


if __name__ == "__main__":
    unittest.main()
