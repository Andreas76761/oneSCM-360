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
                     "Hinweis Achtung", "Hinweis Konflikt", "Hinweis Nicht aktiviert", "Hinweis Belegt", "Box Voraussetzung",
                     "Box Ergebnis", "Box Quelle", "Box Intern", "Box Verweis", "Platzhalter Bild", "oneSCM Tabelle", "Badge", "Untertitel EN"):
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
        texts = [p.text for p in document.paragraphs]
        self.assertIn("⏳ [OFFEN – VALIDIERUNG ERFORDERLICH] Diese Angabe muss vom Fachbereich bestätigt werden.", texts)  # Word symbol fallback
        self.assertEqual(next(p for p in document.paragraphs if p.text.startswith("➜")).style.name, "Box Verweis")


class IconTests(AppCase, unittest.TestCase):
    def test_icon_set(self):
        schema = self.client.get("/api/design/schema").get_json()
        names = [i["name"] for i in schema["icons"]]
        self.assertEqual(len(names), 79)  # 33 own + 40 document symbols + 6 roles
        self.assertEqual(sum(1 for i in schema["icons"] if i["set"] == "document"), 40)
        self.assertEqual({i["role"] for i in schema["icons"] if i["set"] == "roles"}, {"Dealer", "MO", "Market", "HQ", "IT", "intern"})
        self.assertEqual(len(schema["flags"]), 12)
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
        self.assertEqual(len([n for n in archive.namelist() if n.endswith(".svg")]), len(icons.ICONS) + 12)
        self.assertIn("onescm_icons/Dokumentsymbole/LIZENZ.txt", archive.namelist())
        self.assertIn("ISC License", archive.read("onescm_icons/Dokumentsymbole/LIZENZ.txt").decode())
        self.assertIn("onescm_icons/Flaggen/flagge_de.svg", archive.namelist())
        lucide = self.client.get("/api/design/icons/role-dealer.svg").get_data(as_text=True)
        self.assertIn('stroke-width="2"', lucide)
        flag = self.client.get("/api/design/flags/de.svg")
        self.assertEqual(flag.mimetype, "image/svg+xml")
        self.assertEqual(self.client.get("/api/design/flags/xx.svg").status_code, 404)

    def test_vendored_icons_are_sanitised(self):
        for name, icon in icons.ICONS.items():
            for tag, attrs in icons._elements(icon):
                self.assertIn(tag, ("path", "circle", "rect", "line", "polyline", "polygon", "ellipse"), name)
                self.assertFalse(any(k.startswith("on") or "href" in k for k in attrs), name)


class MigrationTests(unittest.TestCase):
    def test_version_1_templates_get_boxes_and_keep_own_values(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            old = json.loads((ROOT / "design_templates.json").read_text(encoding="utf-8"))
            for t in old["templates"]:
                t.pop("boxes", None)
                for k in ("boxStyle", "iconStyle", "tableHeadStyle", "badgeShape"):
                    t["elements"].pop(k, None)
            old["templates"][0]["colors"]["navy"] = "#123456"
            old["templates"].append({**old["templates"][0], "id": "eigene", "name": "Eigene"})
            old["version"] = 1
            data = Path(tmp) / "design_templates.json"
            data.write_text(json.dumps(old), encoding="utf-8")
            svc = design_service.DesignService(ROOT / "design_templates.json", data, Path(tmp) / "backups")
            t = svc.get("handbuch")
            self.assertEqual(len(t["boxes"]), 12)
            self.assertEqual(t["colors"]["navy"], "#123456")
            self.assertEqual(svc.get("releaseletter")["elements"]["boxStyle"], "frame")
            self.assertEqual(len(svc.get("eigene")["boxes"]), 12)
            self.assertEqual(json.loads(data.read_text(encoding="utf-8"))["version"], 2)
            self.assertTrue(list((Path(tmp) / "backups").glob("design-*.json")))


class LayoutBoxTests(AppCase, unittest.TestCase):
    def template(self, tid="handbuch"):
        return self.client.get(f"/api/design/templates/{tid}").get_json()

    def test_twelve_boxes_from_the_pattern(self):
        boxes = {b["id"]: b for b in self.template()["boxes"]}
        self.assertEqual(list(boxes), ["info", "tip", "open", "warn", "conflict", "off", "ok", "pre", "res", "src", "int", "next"])
        self.assertEqual((boxes["tip"]["color"], boxes["tip"]["background"], boxes["tip"]["wordStyle"]), ("#0E7C66", "#E3F4EF", "Hinweis Tipp"))
        self.assertEqual((boxes["int"]["color"], boxes["int"]["symbol"], boxes["next"]["wordStyle"]), ("#9D174D", "🔒", "Box Verweis"))
        self.assertEqual(boxes["open"]["alternatives"], ["doc-clock", "doc-hourglass", "doc-flag"])

    def test_box_validation_and_editing(self):
        t = self.template()
        t["boxes"][1].update(color="#123456", title="Praxistipp:", icon="doc-star", symbol="★")
        saved = self.put("/api/design/templates/handbuch", t).get_json()
        self.assertEqual((saved["boxes"][1]["color"], saved["boxes"][1]["title"], saved["boxes"][1]["icon"]), ("#123456", "Praxistipp:", "doc-star"))
        self.assertEqual(saved["boxes"][1]["purpose"], "Arbeitserleichterung")  # purpose stays as defined
        for change, message in ((("color", "blau"), "HEX"), (("icon", "skull"), "Icon"), (("wordStyle", "Hinweis Info"), "doppelt")):
            bad = json.loads(json.dumps(t))
            bad["boxes"][2][change[0]] = change[1]
            r = self.put("/api/design/templates/handbuch", bad)
            self.assertEqual(r.status_code, 400)
            self.assertIn(message, r.get_json()["error"])
        legacy = {k: v for k, v in t.items() if k != "boxes"}  # templates from older versions get the default boxes
        self.assertEqual(len(design_service.validate(legacy)["boxes"]), 12)

    def test_styles_change_the_css(self):
        t = self.template()
        css = lambda **el: design_service.css(design_service.validate({**t, "elements": {**t["elements"], **el}}))
        self.assertIn("border-left:4px solid var(--c)", css(boxStyle="bar"))
        self.assertIn(".box{background:var(--c);color:#fff}", css(boxStyle="fill"))
        self.assertIn("box-shadow:0 1px 4px", css(boxStyle="card"))
        self.assertIn(".icw{background:var(--c);color:#fff !important;border-radius:50%", css(iconStyle="solid"))
        self.assertIn(".box .icw{display:none}", css(iconStyle="none"))
        self.assertIn("th{background:none;color:var(--navy)", css(tableHeadStyle="lines"))
        self.assertIn(".badge{border-radius:2px}", css(badgeShape="square"))
        self.assertIn("svg{stroke-width:2.2}", css(iconStroke=2.2))
        self.assertIn("aspect-ratio:16/10", css(placeholderRatio="16:10"))
        for bad in ({"boxStyle": "neon"}, {"iconStyle": "3d"}):
            self.assertEqual(design_service.validate({**t, "elements": {**t["elements"], **bad}})["elements"]["boxStyle"], "bar")

    def test_pattern_sections_and_variables(self):
        page = self.client.get("/api/design/templates/handbuch/pattern.html").get_data(as_text=True)
        for text in ("4 Layoutboxen", "8 Spezifikation je Layoutbox", "9 Icon-Bibliothek", "Box Voraussetzung", "Vor Veröffentlichung entfernen.",
                     'alt="Flagge Deutschland"', "MO (Market Operations)", "Dokumentsymbole (Lucide) (40)", "Lucide (ISC-Lizenz)"):
            self.assertIn(text, page)
        css = self.client.get("/api/design/templates/training/variables.css").get_data(as_text=True)
        self.assertIn("--navy: #0B2A4A;", css)
        self.assertIn(".box-pre { --c: #2F5DA8; --bg: #E6EDF8; } /* Voraussetzung · Word: Box Voraussetzung */", css)


class DesignedManualTests(AppCase, unittest.TestCase):
    def test_manual_uses_selected_design(self):
        self.upload(CH01_HTML, "ch01.html")
        handbook = self.client.get("/api/manual/CH01/preview?stage=Draft").get_data(as_text=True)
        self.assertIn("oneSCM Benutzerhandbuch · Kapitel 01", handbook)
        training = self.client.get("/api/manual/CH01/preview?stage=Draft&design=training").get_data(as_text=True)
        self.assertIn("oneSCM Training · Modul 01", training)
        self.assertIn("font-size:12pt", training)
        self.assertEqual(self.client.get("/api/manual/CH01/preview?design=fehlt").status_code, 404)
        self.assertIn('class="box bx-open"', handbook)  # open-validation layout box
        self.assertIn('<span class="rb"><svg aria-hidden="true"><use href="#i-role-dealer"/></svg>Dealer</span>', handbook)  # role badge
        r = self.post("/api/manual/CH01", {"stage": "Draft", "design": "releaseletter"}).get_json()
        self.assertEqual(r["stats"]["design"], "oneSCM Release Letter")


if __name__ == "__main__":
    unittest.main()
