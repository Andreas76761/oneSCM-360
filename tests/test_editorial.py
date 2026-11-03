import copy
import io
from pathlib import Path
import tempfile
import unittest
import zipfile

import app
import editorial


class EditorialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = app.Store(Path(self.temp.name) / "editorial.sqlite3")
        self.outline = app.new_outline("Handbuch")
        self.outline["chapters"] = [app.chapter("Verträge", mandatory=True), app.chapter("Details", 2)]
        self.block = app.block()
        self.block.update(text="Originaltext", status="Freigegeben")
        self.outline["chapters"][0]["blocks"] = [self.block]
        self.outline = self.store.save(self.outline)

    def tearDown(self):
        self.temp.cleanup()

    def test_reimport_requires_decision_and_keeps_content_and_chunk_links(self):
        source = self.store.sources.upload("test.txt", b"Text", {})
        chunk = self.store.sources.chunks(source["id"])[0]
        self.store.sources.review({"id": chunk["id"], "revision": chunk["revision"],
            "labels": {"roles": ["Retailer"], "domains": [], "keywords": [], "labels": [], "topic": ""},
            "assignments": [{"outline_id": self.outline["id"], "chapter_id": self.outline["chapters"][0]["id"]}]}, set())
        rows, _ = app.parse_outline("1 Details\n2 Serviceverträge\n3 Neu")
        result = editorial.reimport(self.outline, rows)
        self.assertEqual(len(result["unresolved"]), 2)
        decisions = {rows[0]["id"]: self.outline["chapters"][1]["id"],
                     rows[1]["id"]: self.outline["chapters"][0]["id"], rows[2]["id"]: "new"}
        result = editorial.reimport(self.outline, rows, decisions)
        self.assertEqual(result["unresolved"], [])
        self.assertEqual(result["comparison"]["counts"]["renamed"], 1)
        saved = self.store.save(result["outline"])
        self.assertEqual(saved["chapters"][1]["blocks"][0]["text"], "Originaltext")
        self.assertEqual(len(self.store.sources.index()[0]["assignments"]), 1)
        self.assertEqual(self.store.snapshot(saved["id"], 1)["chapters"][0]["title"], "Verträge")

    def test_unmatched_chapters_are_retained_and_duplicate_choices_rejected(self):
        rows, _ = app.parse_outline("1 Neu")
        result = editorial.reimport(self.outline, rows, {rows[0]["id"]: "new"})
        self.assertEqual(len(result["retained"]), 2)
        self.assertEqual([c["level"] for c in result["outline"]["chapters"]], [1, 1, 2])
        rows, _ = app.parse_outline("1 A\n2 B")
        with self.assertRaises(app.Invalid):
            editorial.reimport(self.outline, rows, {c["id"]: self.outline["chapters"][0]["id"] for c in rows})

    def test_titles_conditions_and_manual_parent_exclude_subtree(self):
        c = self.outline["chapters"][0]
        c["config"]["titles"] = {"de": "Serviceverträge", "en": "Service contracts"}
        c["config"]["conditions"] = {"role": ["HQ"]}
        child = self.outline["chapters"][1]
        child["blocks"] = [dict(app.block(), text="Unterkapitel")]
        plan = app.compose(self.outline, app.profile())
        self.assertFalse(any(c["visible"] for c in plan["chapters"]))
        p = dict(app.profile(), role="HQ")
        self.assertEqual(app.compose(self.outline, p)["chapters"][0]["title"], "Serviceverträge")
        c["config"].update(inclusion="Manuell", selected=False)
        self.assertFalse(any(c["visible"] for c in app.compose(self.outline, p)["chapters"]))

    def test_scope_variants_essential_instructions_and_custom_depth(self):
        b = self.outline["chapters"][0]["blocks"][0]
        b.update(content_kind="Warnhinweis", scope="Ausführlich")
        b["variants"] = {"Kompakt": {"text": "Kurzer Hinweis", "status": "Entwurf"}}
        plan = app.compose(self.outline, dict(app.profile(), scope="Kompakt"))
        self.assertEqual(plan["chapters"][0]["blocks"][0]["text"], "Kurzer Hinweis")
        self.assertTrue(editorial.release_errors(plan))
        b["variants"] = {}
        self.assertEqual(app.compose(self.outline, dict(app.profile(), scope="Kompakt"))["chapters"][0]["blocks"][0]["text"], "Originaltext")
        b.update(content_kind="Hintergrund", scope="*")
        self.assertEqual(app.compose(self.outline, dict(app.profile(), scope="Kompakt"))["chapters"][0]["blocks"], [])
        self.outline["scope_rules"] = editorial.scope_defaults()
        self.outline["scope_rules"]["Kompakt"].append("Hintergrund")
        self.assertTrue(app.compose(self.outline, dict(app.profile(), scope="Kompakt"))["chapters"][0]["blocks"])

    def test_release_gate_draft_revision_and_immutable_export_usage(self):
        with self.assertRaises(app.Invalid):
            self.store.save(self.outline, releasing=True)
        self.outline["chapters"][0]["config"]["status"] = "Freigegeben"
        approved = self.store.save(self.outline, releasing=True)
        self.assertEqual(approved["metadata"]["status"], "Freigegeben")
        plan = app.compose(approved, approved["profile"])
        plan["draft"] = False
        artifact = app.office_export(plan, "docx")
        eid = self.store.record_export(plan, "docx", artifact)
        approved["chapters"][0]["title"] = "Geändert"
        saved = self.store.save(approved)
        self.assertEqual(saved["metadata"]["status"], "Entwurf")
        self.assertEqual(self.store.snapshot(saved["id"], 2)["metadata"]["status"], "Freigegeben")
        usage = self.store.usage(saved["id"])
        self.assertEqual(usage["exports"][0]["id"], eid)
        self.assertEqual(usage["exports"][0]["revision"], 2)
        with zipfile.ZipFile(io.BytesIO(artifact)) as archive:
            xml = archive.read("word/document.xml").decode()
        self.assertIn("FREIGEGEBENE AUSGABE", xml)
        self.assertIn("Verträge", xml)
        self.assertNotIn("Geändert", xml)

    def test_toc_generated_from_actual_visible_output_and_missing_media_blocks(self):
        toc = app.chapter("Inhaltsverzeichnis", mandatory=True)
        toc["config"] = dict(editorial.defaults(toc), generator="Inhaltsverzeichnis", kind="Automatisch")
        self.outline["chapters"].insert(0, toc)
        plan = app.compose(self.outline, app.profile())
        text = plan["chapters"][0]["blocks"][0]["text"]
        self.assertIn("2 Verträge", text)
        self.assertNotIn("Details", text)
        self.outline["chapters"][1]["config"]["expected"] = ["Bild", "Klickstrecke"]
        self.assertTrue(any("Bild" in w for w in app.compose(self.outline, app.profile())["warnings"]))

    def library_entry(self, **values):
        b = dict(self.block, **values)
        return self.store.library.save({"id": app.uid(), "revision": 0, "title": "Zentral", "block": b})

    def test_library_pins_revision_and_never_broadens_internal_content(self):
        entry = self.library_entry(internal=True, role="HQ")
        c = self.outline["chapters"][0]
        c["blocks"] = [{**entry["block"], "id": app.uid(), "library_ref": {"id": entry["id"], "revision": 1}}]
        c["blocks"][0].update(internal=False, role="*", text="Manipuliert")
        saved = self.store.save(self.outline)
        self.assertTrue(saved["chapters"][0]["blocks"][0]["internal"])
        self.assertEqual(app.compose(saved, app.profile())["chapters"][0]["blocks"], [])
        entry["block"]["text"] = "Neue zentrale Fassung"
        self.store.library.save(entry)
        self.assertEqual(self.store.get(saved["id"])["chapters"][0]["blocks"][0]["text"], "Originaltext")
        self.assertEqual(self.store.library.listing()[0]["usage"][0]["revision"], 1)
        with self.assertRaises(app.Conflict):
            self.store.library.save(entry)

    def test_assignment_restrictions_intersect_and_notes_are_excluded(self):
        entry = self.library_entry(role="HQ")
        b = {**entry["block"], "id": app.uid(), "library_ref": {"id": entry["id"], "revision": 1},
             "assignment": {"conditions": {"role": ["Retailer"]}, "note": "SECRET_NOTE"}}
        self.outline["chapters"][0]["blocks"] = [b]
        saved = self.store.save(self.outline)
        for role in ["Retailer", "HQ"]:
            self.assertEqual(app.compose(saved, dict(app.profile(), role=role))["chapters"][0]["blocks"], [])
        b["assignment"]["conditions"] = {"role": ["HQ"]}
        self.outline["revision"] = saved["revision"]
        saved = self.store.save(self.outline)
        plan = app.compose(saved, dict(app.profile(), role="HQ"))
        for fmt in ["docx", "pptx"]:
            with zipfile.ZipFile(io.BytesIO(app.office_export(plan, fmt))) as archive:
                self.assertNotIn("SECRET_NOTE", "".join(archive.read(f).decode() for f in archive.namelist() if f.endswith(".xml")))
        self.assertEqual(plan["manifest"]["texts"][0]["library_ref"]["revision"], 1)

    def test_glossary_collection_uses_domains_mandatory_terms_and_pinned_revisions(self):
        glossary = self.outline["chapters"][0]
        glossary["config"]["generator"] = "Glossar"
        glossary["mappings"] = [{"target_id": "d3", "active": True}]
        items = []
        for title, domain, mandatory, role in [("Passend", "d3", False, "*"),
                                               ("Pflichtbegriff", "d1", True, "*"),
                                               ("Fremddomäne", "d1", False, "*"),
                                               ("HQ Begriff", "d3", True, "HQ")]:
            items.append(self.store.library.save({"id": app.uid(), "revision": 0, "title": title,
                "domains": [domain], "mandatory_term": mandatory,
                "block": dict(app.block(), text="Definition", status="Freigegeben", role=role, content_kind="Glossarbegriff")}))
        proposal = self.store.library.collection(self.outline, glossary["id"])
        self.assertEqual({b["library_title"] for b in proposal["blocks"]}, {"Passend", "Pflichtbegriff"})
        glossary["blocks"].extend(proposal["blocks"])
        saved = self.store.save(self.outline)
        self.assertEqual(self.store.library.collection(saved, glossary["id"])["blocks"], [])
        texts = [b["text"] for b in app.compose(saved, app.profile())["chapters"][0]["blocks"]]
        self.assertIn("Passend\nDefinition", texts)


if __name__ == "__main__":
    unittest.main()
