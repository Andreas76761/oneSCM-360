"""Durable orchestration must preserve review boundaries and reject stale inputs."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import app
import sources


class JobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = app.Store(Path(self.temp.name) / "jobs.sqlite3")
        outline = app.new_outline("Agententest")
        outline["chapters"] = [app.chapter("Contract management")]
        self.outline = self.store.save(outline)
        self.source = self.store.sources.upload("Jira.html", b"<html><body><p>SCM-123 Contract management for dealer. Open the contract.</p></body></html>", {"kind": "Jira"})
        self.source_two = self.store.sources.upload("Manual.txt", b"Customer management for HQ. Review the customer record.", {"kind": "Datei"})

    def tearDown(self):
        self.temp.cleanup()

    def start(self, **extra):
        return self.store.orchestrator.start({"outline_id": self.outline["id"], "sources": [self.source["id"], self.source_two["id"]],
            "mode": "rules", "agents": ["triage", "structure", "media", "quality"], **extra})

    def finish(self, row):
        for _ in range(30):
            if row["status"] in ["review", "failed", "cancelled", "completed"]:
                break
            row = self.store.orchestrator.step(row["id"])
        self.assertEqual(row["status"], "review", row.get("error"))
        return row

    def test_agent_steps_leave_content_unmodified_until_explicit_review(self):
        initial = copy.deepcopy(self.store.get(self.outline["id"]))
        row = self.finish(self.start())
        self.assertEqual(self.store.get(self.outline["id"]), initial)
        self.assertEqual(self.store.library.listing(), [])
        before = self.store.sources.chunks(self.source["id"])[0]
        self.assertEqual(before["labels"], {})
        self.assertEqual(before["assignments"], [])
        self.assertTrue(row["candidates"][0]["labels"]["chapter_ids"])
        reviewed = self.store.orchestrator.apply({"id": row["id"], "selected": [before["id"]], "create_drafts": True})
        self.assertEqual(reviewed["status"], "completed")
        after = self.store.sources.chunks(self.source["id"])[0]
        self.assertEqual(after["labels"]["roles"], ["Retailer"])
        self.assertEqual(after["revision"], before["revision"] + 1)
        self.assertTrue(after["assignments"])
        self.assertEqual(self.store.sources.chunks(self.source_two["id"])[0]["labels"], {})
        entry = self.store.library.listing()[0]
        self.assertEqual(entry["block"]["status"], "Entwurf")
        self.assertFalse(entry["block"]["evidence"][0]["verified"])
        self.assertEqual(entry["agent_provenance"]["chunk_revision"], before["revision"])
        self.assertEqual(self.store.get(self.outline["id"]), initial)
        with self.assertRaises(app.Conflict):
            self.store.orchestrator.apply({"id": row["id"], "selected": [before["id"]]})

    def test_changed_outline_blocks_application_without_partial_writes(self):
        row = self.finish(self.start())
        changed = self.store.get(self.outline["id"])
        changed["title"] = "Neue Revision"
        self.store.save(changed)
        with self.assertRaises(app.Conflict):
            self.store.orchestrator.apply({"id": row["id"], "selected": [c["id"] for c in row["candidates"]], "create_drafts": True})
        self.assertEqual(self.store.library.listing(), [])
        self.assertTrue(all(not c["labels"] for c in self.store.sources.index()))

    def test_changed_taxonomy_or_chunk_and_deleted_source_are_rejected(self):
        for mutate in ["taxonomy", "chunk", "delete"]:
            with self.subTest(mutate=mutate):
                source = self.store.sources.upload(f"extra-{mutate}.txt", ("Contract " + mutate).encode(), {})
                row = self.finish(self.start(sources=[source["id"]]))
                chunk = self.store.sources.chunks(source["id"])[0]
                if mutate == "taxonomy":
                    taxonomy = self.store.taxonomy()
                    self.store.save_taxonomy({"revision": taxonomy["revision"], "subdomains": taxonomy["subdomains"]})
                elif mutate == "chunk":
                    self.store.sources.review({"id": chunk["id"], "revision": chunk["revision"],
                        "labels": {"roles": [], "domain_ids": [], "keywords": [], "labels": [], "topic": "Reviewed"}, "assignments": []}, set())
                else:
                    self.store.sources.delete(source["id"])
                with self.assertRaises(app.Conflict):
                    self.store.orchestrator.apply({"id": row["id"], "selected": [chunk["id"]]})

    def test_cancellation_discards_inflight_result_and_never_applies(self):
        row = self.start(agents=["triage"], sources=[self.source["id"]])
        real_rules = sources.rules

        def cancel_during_work(chunk, outline, targets):
            self.store.orchestrator.cancel(row["id"])
            return real_rules(chunk, outline, targets)

        with patch("orchestration.sources.rules", side_effect=cancel_during_work):
            stopped = self.store.orchestrator.step(row["id"])
        self.assertEqual(stopped["status"], "cancelled")
        self.assertEqual(stopped["index"], 0)
        self.assertEqual(self.store.orchestrator.step(row["id"])["status"], "cancelled")
        with self.assertRaises(app.Conflict):
            self.store.orchestrator.apply({"id": row["id"], "selected": [row["candidates"][0]["id"]]})

    def test_failed_ai_step_can_retry_without_silent_rule_fallback(self):
        row = self.start(mode="ollama", model="local-test-model", agents=["triage"], sources=[self.source["id"]])
        with patch("orchestration.sources.ollama_suggestion", side_effect=ValueError("Lokales Modell nicht erreichbar")), patch("orchestration.sources.rules") as fallback:
            failed = self.store.orchestrator.step(row["id"])
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["index"], 0)
        fallback.assert_not_called()
        proposal = sources.rules(row["chunks"][0], row["outline"], row["targets"])
        with patch("orchestration.sources.ollama_suggestion", return_value=proposal):
            recovered = self.store.orchestrator.step(row["id"])
        self.assertEqual(recovered["status"], "review")
        self.assertEqual(self.store.sources.chunks(self.source["id"])[0]["labels"], {})

    def test_restart_marks_interrupted_step_paused_and_preserves_progress(self):
        row = self.start()
        row = self.store.orchestrator.step(row["id"])
        self.assertEqual(row["index"], 1)
        row["status"] = "running"
        with self.store.connect() as db:
            db.execute("UPDATE agent_jobs SET payload=? WHERE id=?", (json.dumps(row), row["id"]))
        restarted = app.Store(Path(self.temp.name) / "jobs.sqlite3")
        restored = restarted.orchestrator.get(row["id"])
        self.assertEqual(restored["status"], "paused")
        self.assertEqual(restored["index"], 1)
        self.assertEqual(restored["steps"][0]["status"], "done")

    def test_translation_proposal_stays_draft_and_quality_runs_after_it(self):
        row = self.start(agents=["translation", "quality"], model="local-test-model", sources=[self.source["id"]], target_language="fr")
        self.assertEqual([s["agent"] for s in row["steps"]], ["translation", "quality"])
        with patch("orchestration.language_workflow.generate", return_value={"text": "Ouvrez le contrat.", "status": "Entwurf", "source_revision": 1}):
            row = self.finish(row)
        self.assertEqual(row["candidates"][0]["language"], "fr")
        self.assertEqual(row["candidates"][0]["text"], "Ouvrez le contrat.")
        self.assertEqual(self.store.library.listing(), [])
        result = self.store.orchestrator.apply({"id": row["id"], "selected": [row["candidates"][0]["id"]], "create_drafts": True})
        self.assertEqual(result["status"], "completed")
        self.assertEqual(self.store.library.listing()[0]["block"]["status"], "Entwurf")


if __name__ == "__main__":
    unittest.main()
