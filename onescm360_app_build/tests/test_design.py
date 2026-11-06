import io
import json
import unittest
import zipfile

from helpers import CH01_HTML, ROOT, AppCase, H
from services import design_service, icons, word_template

SHIPPED = ["handbuch", "releaseletter", "quickreference", "training"]


class DesignTemplateTests(AppCase, unittest.TestCase):
    def template(self, tid="handbuch"):
        return self.client.get(f"/api/design/templates/{tid}").get_json()

    def test_shipped_templates_and_pattern_values(self):
        templates = self.client.get("/api/design/templates").get_json()
        self.assertEqual([t["id"] for t in templates], SHIPPED)
        self.assertTrue(all(t["shipped"] for t in templates))
        hb = self.template()
        # values from the design pattern specification
        self.assertEqual((hb["fonts"]["heading"], hb["fonts"]["body"]), ("Segoe UI", "Calibri"))
        self.assertEqual((hb["typography"]["title"]["size"], hb["typography"]["h1"]["size"], hb["typography"]["h2"]["size"],
                          hb["typography"]["body"]["size"], hb["typography"]["source"]["size"]), (28, 20, 14, 11, 8.5))
        self.assertEqual((hb["typography"]["body"]["lineHeight"], hb["typography"]["h1"]["before"], hb["typography"]["h1"]["after"]), (1.35, 24, 10))
        self.assertEqual((hb["colors"]["navy"], hb["colors"]["petrol"], hb["colors"]["warn"], hb["colors"]["van"]),
                         ("#0B2A4A", "#00708A", "#B26A00", "#7A4FB5"))
        self.assertEqual((hb["page"]["marginLeft"], hb["page"]["marginTop"]), (2.5, 2.0))
        self.assertEqual(hb["header"], "oneSCM Benutzerhandbuch · Kapitel {chapter}")
        qr = self.template("quickreference")
        self.assertEqual((qr["page"]["orientation"], qr["page"]["columns"]), ("landscape", 2))
        self.assertTrue((self.tmp / "data" / "design_templates.json").exists())

    def test_crud_reset_and_program_folder_untouched(self):
        shipped = (ROOT / "design_templates.json").read_bytes()
        created = self.post("/api/design/templates", {"baseId": "handbuch", "name": "Handbuch Marke B"})
        self.assertEqual(created.status_code, 201, created.get_json())
        t = created.get_json()
        self.assertEqual((t["id"], t["shipped"], t["name"]), ("handbuch-marke-b", False, "Handbuch Marke B"))
        t["colors"]["navy"] = "#112233"
        t["typography"]["h1"]["size"] = 22
        t["fonts"]["heading"] = "Aptos"
        updated = self.put(f"/api/design/templates/{t['id']}", t).get_json()
        self.assertEqual((updated["colors"]["navy"], updated["typography"]["h1"]["size"], updated["fonts"]["heading"]), ("#112233", 22, "Aptos"))
        hb = self.template()
        hb["typography"]["body"]["size"] = 12
        self.put("/api/design/templates/handbuch", hb)
        self.assertEqual(self.template()["typography"]["body"]["size"], 12)
        self.assertEqual(self.post("/api/design/templates/handbuch/reset", {}).get_json()["typography"]["body"]["size"], 11)
        self.assertEqual(self.post(f"/api/design/templates/{t['id']}/reset", {}).status_code, 400)  # own templates have no shipped state
        self.assertEqual(self.delete(f"/api/design/templates/{t['id']}").status_code, 200)
        self.assertEqual(self.client.get(f"/api/design/templates/{t['id']}").status_code, 404)
        self.assertEqual((ROOT / "design_templates.json").read_bytes(), shipped)
        self.assertTrue(list((self.tmp / "data" / "backups").glob("design-*.json")))

    def test_validation_blocks_injection(self):
        t = self.template()
        cases = [("colors", "navy", "red;}body{display:none"), ("fonts", "heading", "Comic Sans'};x{"),
                 ("typography", "h1", {**t["typography"]["h1"], "size": 200}), ("typography", "body", {**t["typography"]["body"], "color": "url(x)"}),
                 ("page", "marginLeft", 9)]
        for section, key, value in cases:
            bad = json.loads(json.dumps(t))
            bad[section][key] = value
            r = self.put("/api/design/templates/handbuch", bad)
            if section == "fonts":  # unknown fonts fall back to the default instead of being stored
                self.assertEqual(r.get_json()["fonts"]["heading"], "Segoe UI")
                continue
            self.assertEqual(r.status_code, 400, (section, key))
        bad = json.loads(json.dumps(t))
        bad["header"] = "Handbuch {secret}"
        self.assertIn("Platzhalter", self.put("/api/design/templates/handbuch", bad).get_json()["error"])
        bad = json.loads(json.dumps(t))
        bad["icons"]["info"] = "skull"
        self.assertEqual(self.put("/api/design/templates/handbuch", bad).status_code, 400)
        bad = json.loads(json.dumps(t))
        bad["name"] = "<script>"
        page = design_service.pattern_html(design_service.validate(bad))
        self.assertNotIn("<script>", page)
        for tid in SHIPPED[1:]:
            self.delete(f"/api/design/templates/{tid}")
        self.assertEqual(self.delete("/api/design/templates/handbuch").status_code, 400)  # last one stays

    def test_preview_pattern_and_exports(self):
        t = self.template()
        t["colors"]["petrol"] = "#AA0055"
        r = self.post("/api/design/preview", t).get_json()
        page = self.client.get(r["url"])
        self.assertEqual(page.status_code, 200)
        self.assertIn("default-src 'none'", page.headers["Content-Security-Policy"])
        text = page.get_data(as_text=True)
        self.assertIn("--petrol:#AA0055", text)  # unsaved preview uses the edited values
        self.assertIn("[OFFEN – VALIDIERUNG ERFORDERLICH]", text)
        self.assertIn("Segoe UI 14 pt", text)
        self.assertEqual(self.client.get("/api/design/preview/deadbeef00000000").status_code, 404)
        pattern = self.client.get("/api/design/templates/training/pattern.html")
        self.assertIn("attachment", pattern.headers["Content-Disposition"])
        exported = json.loads(self.client.get("/api/design/templates/releaseletter/export.json").data)
        self.assertNotIn("id", exported)
        imported = self.client.post("/api/design/templates/import", data={"file": (io.BytesIO(json.dumps({**exported, "name": "Import RL"}).encode()), "rl.json")},
                                    headers=H, content_type="multipart/form-data")
        self.assertEqual(imported.status_code, 201, imported.get_json())
        self.assertEqual(imported.get_json()["typography"]["h1"]["size"], 16)
        broken = self.client.post("/api/design/templates/import", data={"file": (io.BytesIO(b"{kaputt"), "x.json")}, headers=H, content_type="multipart/form-data")
        self.assertEqual(broken.status_code, 400)

    def test_word_template(self):
        dotx = self.client.get("/api/design/templates/quickreference/word.dotx")
        self.assertEqual(dotx.status_code, 200)
        archive = zipfile.ZipFile(io.BytesIO(dotx.data))
        self.assertIn(b"template.main+xml", archive.read("[Content_Types].xml"))
        styles = archive.read("word/styles.xml").decode()
        for name in ("heading 1", "heading 2", "heading 3", "caption", "Quellenzeile", "Hinweis Info", "Hinweis Tipp", "Hinweis Offen",
                     "Hinweis Kritisch", "oneSCM Tabelle", "Badge", "Untertitel EN"):
            self.assertIn(f'w:val="{name}"', styles)
        document = archive.read("word/document.xml").decode()
        self.assertIn('w:orient="landscape"', document)
        self.assertIn('<w:cols w:num="2"', document)
        self.assertIn('w:instr=" PAGE "', archive.read("word/footer1.xml").decode())  # quick reference: "Seite {page}" only
        handbook = zipfile.ZipFile(io.BytesIO(self.client.get("/api/design/templates/handbuch/word.dotx").data))
        footer = handbook.read("word/footer1.xml").decode()
        self.assertIn('w:instr=" NUMPAGES "', footer)
        self.assertIn("Version V.X | Stand TT.MM.JJJJ | Seite ", footer)
        self.assertEqual(self.client.get("/api/design/templates/handbuch/word.pdf").status_code, 400)

    def test_word_document_opens_with_styles(self):
        try:
            import docx  # optional: python-docx is a dependency of the handbook app in the repository root
        except ImportError:
            self.skipTest("python-docx nicht installiert")
        data = word_template.build(design_service.validate(self.template("training")), "docx")
        document = docx.Document(io.BytesIO(data))
        self.assertEqual(document.styles["Heading 1"].font.size.pt, 22)
        self.assertEqual(document.styles["Normal"].font.size.pt, 12)
        self.assertEqual(round(document.sections[0].top_margin.cm, 1), 2.5)
        self.assertIn("Hinweis Offen", {s.name for s in document.styles})


class IconTests(AppCase, unittest.TestCase):
    def test_icon_set(self):
        schema = self.client.get("/api/design/schema").get_json()
        names = [i["name"] for i in schema["icons"]]
        self.assertGreaterEqual(len(names), 30)
        for required in ("info", "lightbulb", "pending", "warning", "report", "verified", "toggle_off", "badge", "hub", "description",
                         "screenshot", "image", "process", "car", "van"):
            self.assertIn(required, names)
        svg = self.client.get("/api/design/icons/verified.svg?color=%231E7F4F")
        self.assertEqual(svg.mimetype, "image/svg+xml")
        body = svg.get_data(as_text=True)
        self.assertIn('stroke="#1E7F4F"', body)
        self.assertNotIn("currentColor", body)  # explicit colour for Word
        self.assertIn('stroke="#00708A"', self.client.get("/api/design/icons/info.svg?color=red").get_data(as_text=True))  # invalid → default
        self.assertEqual(self.client.get("/api/design/icons/skull.svg").status_code, 404)
        archive = zipfile.ZipFile(io.BytesIO(self.client.get("/api/design/icons.zip").data))
        self.assertEqual(len([n for n in archive.namelist() if n.endswith(".svg")]), len(icons.ICONS))


class DesignedManualTests(AppCase, unittest.TestCase):
    def test_manual_uses_selected_design(self):
        self.upload(CH01_HTML, "ch01.html")
        handbook = self.client.get("/api/manual/CH01/preview?stage=Draft").get_data(as_text=True)
        self.assertIn("oneSCM Benutzerhandbuch · Kapitel 01", handbook)
        training = self.client.get("/api/manual/CH01/preview?stage=Draft&design=training").get_data(as_text=True)
        self.assertIn("oneSCM Training · Modul 01", training)
        self.assertIn("font-size:12pt", training)
        self.assertEqual(self.client.get("/api/manual/CH01/preview?design=fehlt").status_code, 404)
        r = self.post("/api/manual/CH01", {"stage": "Draft", "design": "releaseletter"}).get_json()
        self.assertEqual(r["stats"]["design"], "oneSCM Release Letter")


if __name__ == "__main__":
    unittest.main()
