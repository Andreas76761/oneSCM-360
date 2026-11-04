"""Internal knowledge must stay separate even for HQ reader profiles."""
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest

from pypdf import PdfReader
import app
import renderers
from version import VERSION
from test_publishing import office_parts


class InternalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=app.Store(Path(self.temp.name)/"test.sqlite3")
        self.entry={"id":"faq-1","revision":0,"title":"Testzugang","body":"PRIVATE_TESTING_INFO",
                    "question":"Wie wird getestet?","answer":"PRIVATE_FAQ_ANSWER", "categories":["internal-testing"],
                    "labels":["Regression"],"roles":["HQ"],"markets":["DE"],"status":"Freigegeben","chatbot_enabled":True}

    def tearDown(self):
        self.temp.cleanup()

    def test_revision_conflict_history_and_persistence(self):
        saved=self.store.internal.save(self.entry)
        with self.assertRaises(app.Conflict):self.store.internal.save(self.entry)
        edited=copy.deepcopy(saved);edited["body"]="Changed"
        self.store.internal.save(edited)
        self.assertEqual(self.store.internal.history(saved["id"])[1]["body"],"PRIVATE_TESTING_INFO")
        reopened=app.Store(self.store.path)
        self.assertEqual(reopened.internal.listing()[0]["revision"],2)

    def test_hierarchy_cycles_and_many_to_many_mapping(self):
        categories=self.store.internal.categories()
        categories["items"].append({"id":"regression","name":"Regression","parent_id":"internal-testing"})
        categories=self.store.internal.save_categories(categories)
        self.entry["categories"]=["regression","internal-it"]
        self.assertEqual(len(self.store.internal.save(self.entry)["categories"]),2)
        categories["items"][0]["parent_id"]="regression"
        with self.assertRaises(app.Invalid):self.store.internal.save_categories(categories)

    def test_only_opted_in_approved_faq_matches_profile(self):
        saved=self.store.internal.save(self.entry)
        self.assertEqual(len(self.store.internal.chatbot_preview({"query":"getestet","role":"HQ","market":"DE","language":"de"})),1)
        self.assertFalse(self.store.internal.chatbot_preview({"role":"Retailer"}))
        self.assertFalse(self.store.internal.chatbot_preview({"market":"FR"}))
        self.assertFalse(self.store.internal.chatbot_preview({"language":"en"}))
        for field,value in [("status","Entwurf"),("status","Archiviert"),("chatbot_enabled",False)]:
            candidate=copy.deepcopy(saved);candidate[field]=value
            saved=self.store.internal.save(candidate)
            self.assertFalse(self.store.internal.chatbot_preview({}))
        saved["chatbot_enabled"]=True;saved["answer"]=""
        with self.assertRaises(app.Invalid):self.store.internal.save(saved)

    def test_register_is_absent_from_all_reader_formats_and_library(self):
        self.store.internal.save(self.entry)
        outline=app.new_outline("Reader manual")
        outline["profile"]["role"]="HQ"
        outline["chapters"]=[app.chapter("Public instructions")]
        outline["chapters"][0]["blocks"]=[dict(app.block(),text="Public content",status="Freigegeben")]
        outline=self.store.save(outline);plan=app.compose(outline,outline["profile"])
        outputs=[json.dumps(plan),json.dumps(self.store.all()),json.dumps(self.store.library.listing()),
                 office_parts(app.office_export(plan,"docx")),office_parts(app.office_export(plan,"pptx")),
                 renderers.html_export(plan).decode()," ".join(p.extract_text() for p in PdfReader(io.BytesIO(renderers.pdf_export(plan))).pages)]
        for output in outputs:
            self.assertNotIn("PRIVATE_TESTING_INFO",output)
            self.assertNotIn("PRIVATE_FAQ_ANSWER",output)

    def test_four_finalization_agents_report_without_publication(self):
        outline=app.new_outline("Final check")
        outline["chapters"]=[app.chapter("Contract")]
        outline["chapters"][0]["blocks"]=[dict(app.block(),text="Open contract",status="Freigegeben")]
        outline=self.store.save(outline)
        job=self.store.orchestrator.start({"outline_id":outline["id"],"agents":["finalization","validation","layout","documentation"]})
        for _ in range(4):job=self.store.orchestrator.step(job["id"])
        self.assertEqual(job["status"],"completed")
        self.assertEqual(len(job["reports"]),4)
        self.assertEqual(self.store.get(outline["id"]),outline)
        self.assertIn(VERSION,job["report_markdown"])

    def test_jira_verification_invalidated_after_content_or_validity_edit(self):
        outline=app.new_outline("Evidence")
        outline["chapters"]=[app.chapter("Contract")]
        outline["chapters"][0]["blocks"]=[dict(app.block(),text="Original",evidence=[{"key":"SCM-1","status":"Done","type":"Story","date":"2026-11-03","verified":True}])]
        saved=self.store.save(outline)
        b=saved["chapters"][0]["blocks"][0]
        self.assertTrue(b["evidence"][0]["verified"])
        saved=self.store.save(saved)
        self.assertTrue(saved["chapters"][0]["blocks"][0]["evidence"][0]["verified"])
        saved["chapters"][0]["blocks"][0]["text"]="Changed"
        saved=self.store.save(saved)
        self.assertFalse(saved["chapters"][0]["blocks"][0]["evidence"][0]["verified"])
