"""Manual AI handoff boundaries, using only synthetic text and fake responses."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import app


class AIExchangeReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = app.Store(Path(self.temp.name) / "exchange.sqlite3")
        self.source = self.store.sources.upload("synthetic.txt", b"Contract management: open the synthetic contract.", {})
        self.chunk = self.store.sources.chunks(self.source["id"])[0]

    def prepare(self, **extra):
        return self.store.ai_exchange.prepare({"provider": "Microsoft 365 Copilot", "task": "Handbuch", "language": "de",
            "role": "Retailer", "market": "DE", "division": "PC", "chunks": [self.chunk["id"]], **extra})

    def response(self, job, **extra):
        return json.dumps({"job_id": job["id"], "title": "Synthetischer Vertragsablauf", "text": "# Vertrag\n\nDen Vertrag öffnen.",
            "source_ids": [self.chunk["id"]], "warnings": ["Fachlich prüfen."], **extra})

    def test_manual_exchange_uses_only_selected_chunks_and_makes_no_network_call(self):
        self.store.sources.upload("unselected.txt", b"PRIVATE_UNSELECTED_SOURCE", {})
        self.store.internal.save({"id": app.uid(), "revision": 0, "title": "Internal only",
            "categories": ["internal-testing"], "body": "PRIVATE_INTERNAL_BODY", "note": "PRIVATE_INTERNAL_NOTE"})
        with patch("socket.socket.connect", side_effect=AssertionError("Unexpected network connection")) as network:
            job = self.prepare()
            preview = self.store.ai_exchange.preview({"id": job["id"], "response": self.response(job)})
            entry = self.store.ai_exchange.accept({"id": job["id"], "response": self.response(job), "reviewed": True})
            network.assert_not_called()
        self.assertIn(self.chunk["text"], job["prompt"])
        for private in ["PRIVATE_UNSELECTED_SOURCE", "PRIVATE_INTERNAL_BODY", "PRIVATE_INTERNAL_NOTE"]:
            self.assertNotIn(private, json.dumps([job, preview, entry]))
        self.assertEqual(self.store.all(), [])
        self.assertEqual(entry["block"]["status"], "Entwurf")

    def test_provider_preparation_and_preview_never_publish_or_modify_sources(self):
        before = copy.deepcopy(self.store.sources.chunks(self.source["id"]))
        for provider in ["Microsoft 365 Copilot", "Claude", "Google Gemini"]:
            job = self.prepare(provider=provider)
            preview = self.store.ai_exchange.preview({"id": job["id"], "response": "```json\n" + self.response(job) + "\n```"})
            self.assertEqual(preview["job"]["provider"], provider)
        self.assertEqual(self.store.library.listing(), [])
        self.assertEqual(self.store.all(), [])
        self.assertEqual(self.store.sources.chunks(self.source["id"]), before)

    def test_invalid_responses_unknown_sources_and_wrong_jobs_are_rejected(self):
        job = self.prepare()
        responses = ["not JSON", "[]", self.response(job, job_id="another-job"),
                     self.response(job, source_ids=[]), self.response(job, source_ids=["unknown-chunk"]),
                     self.response(job, source_ids=[None]), self.response(job, text=""),
                     self.response(job, warnings="not a list")]
        for response in responses:
            with self.subTest(response=response[:80]):
                with self.assertRaises(app.Invalid):
                    self.store.ai_exchange.preview({"id": job["id"], "response": response})
        self.assertEqual(self.store.library.listing(), [])

    def test_only_explicitly_reviewed_response_creates_one_unapproved_unassigned_draft(self):
        outline = self.store.save(app.new_outline("Unchanged outline"))
        job = self.prepare(task="Releaseletter")
        data = {"id": job["id"], "response": self.response(job)}
        for value in [None, False, 1, "true"]:
            with self.subTest(reviewed=value):
                with self.assertRaises(app.Invalid):
                    self.store.ai_exchange.accept({**data, "reviewed": value})
        entry = self.store.ai_exchange.accept({**data, "reviewed": True})
        self.assertEqual(entry["block"]["status"], "Entwurf")
        self.assertEqual(entry["block"]["uses"], {"Handbuch": False, "Releaseletter": True, "Quickreference": False})
        self.assertEqual(self.store.library.listing()[0]["usage"], [])
        self.assertEqual(self.store.get(outline["id"]), outline)
        self.assertTrue(self.store.ai_exchange.get(job["id"])["accepted"])
        with self.assertRaises((app.Invalid, app.Conflict)):
            self.store.ai_exchange.accept({**data, "reviewed": True})
        self.assertEqual(len(self.store.library.listing()), 1)

    def test_changed_or_deleted_source_blocks_acceptance(self):
        for mutation in ["changed", "deleted"]:
            with self.subTest(mutation=mutation):
                job = self.prepare()
                if mutation == "changed":
                    with self.store.connect() as db:
                        db.execute("UPDATE chunks SET text=text||' changed',revision=revision+1 WHERE id=?", (self.chunk["id"],))
                else:
                    self.store.sources.delete(self.source["id"])
                self.assertTrue(self.store.ai_exchange.get(job["id"])["stale"])
                with self.assertRaises(app.Invalid):
                    self.store.ai_exchange.accept({"id": job["id"], "response": self.response(job), "reviewed": True})
        self.assertEqual(self.store.library.listing(), [])

    def test_source_deleted_immediately_after_preview_cannot_pass_commit_recheck(self):
        job = self.prepare()
        data = {"id": job["id"], "response": self.response(job), "reviewed": True}
        original_preview = self.store.ai_exchange.preview
        def race(request):
            result = original_preview(request)
            self.assertFalse(result["job"]["stale"])
            self.store.sources.delete(self.source["id"])
            return result
        with patch.object(self.store.ai_exchange, "preview", side_effect=race):
            with self.assertRaises(app.Invalid):
                self.store.ai_exchange.accept(data)
        self.assertEqual(self.store.library.listing(), [])

    def test_known_pii_fields_are_scrubbed_in_prompt_and_returned_draft(self):
        text = "Reporter: Synthetic Reporter\nAssignee: Synthetic Assignee\nComment author: Synthetic Author\nKontakt fake.person@example.invalid\nLOGIN: synthetic_login_77\nVertrag prüfen."
        source = self.store.sources.upload("pii.txt", text.encode(), {})
        chunk = self.store.sources.chunks(source["id"])[0]
        job = self.prepare(chunks=[chunk["id"]])
        response = self.response(job, text=text, source_ids=[chunk["id"]])
        entry = self.store.ai_exchange.accept({"id": job["id"], "response": response, "reviewed": True})
        for private in ["Synthetic Reporter", "Synthetic Assignee", "Synthetic Author", "fake.person@example.invalid", "synthetic_login_77"]:
            self.assertNotIn(private, job["prompt"])
            self.assertNotIn(private, entry["block"]["text"])
        self.assertIn("Vertrag prüfen.", entry["block"]["text"])

    def test_internal_ticket_keys_and_links_never_enter_reader_draft(self):
        job = self.prepare()
        response = self.response(job, title="Vertrag SYN-123", text="Vertrag öffnen. SYN-123\n[Ticket](https://jira.example.invalid/browse/SYN-123)")
        entry = self.store.ai_exchange.accept({"id": job["id"], "response": response, "reviewed": True})
        reader = entry["title"] + entry["block"]["text"]
        self.assertNotIn("SYN-123", reader)
        self.assertNotIn("jira.example.invalid", reader)
