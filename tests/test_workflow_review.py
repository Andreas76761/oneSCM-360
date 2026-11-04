"""Independent regression review: synthetic data, stale edits and evidence boundaries."""
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import app


class WorkflowReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = app.Store(Path(self.temp.name) / "review.sqlite3")
        self.today = date.today().isoformat()
        self.profile = dict(role="HQ", market="DE", language="de", division="PC",
                            as_of=self.today, environment="prod")

    def faq(self, **changes):
        data = dict(
            id=app.uid(), revision=0, title="Vertragsdauer", question="Welche Vertragsdauer gilt?",
            answer="Die Vertragsdauer beträgt zwölf Monate.", categories=["internal-testing"],
            status="Freigegeben", chatbot_enabled=True, roles=["HQ"], markets=["DE"],
        )
        return self.store.internal.save({**data, **changes})

    def ask(self, **changes):
        return self.store.chat.ask(dict(question="Welche Vertragsdauer gilt?", profile=self.profile, **changes))

    def preprod(self):
        outline = app.new_outline("Synthetisches Handbuch")
        outline["profile"].update(market="DE", environment="preprod", as_of=self.today)
        chapter = app.chapter("Vertrag", mandatory=True)
        chapter["config"] = {"status": "Freigegeben"}
        chapter["blocks"] = [dict(app.block(), text="Den Vertrag öffnen.", status="Freigegeben")]
        outline["chapters"] = [chapter]
        return self.store.save(self.store.save(outline), releasing=True)

    def prepare(self, outline, version="test-1"):
        return self.store.releases.prepare(dict(sources=[outline["id"]], version=version, date=self.today))

    def promote(self, package):
        return self.store.releases.promote(dict(id=package["id"], revision=package["revision"],
                                               acknowledged=True, note="Fachlich geprüft."))

    def prod(self):
        active = self.store.releases.listing()["active"]
        return self.store.get(active["members"][0]["outline_id"])

    def source(self, name="zusatz.txt", text="Zusätzlicher synthetischer Prüfbeleg."):
        source = self.store.sources.upload(name, text.encode(), {})
        return {**self.store.sources.chunks(source["id"])[0], "source_id": source["id"]}

    def assign(self, chunk, outline):
        self.store.sources.review(dict(id=chunk["id"], revision=chunk["revision"], labels={},
                                       assignments=[dict(outline_id=outline["id"], chapter_id=outline["chapters"][0]["id"])]), set())

    def test_promotion_rejects_new_prod_only_assignment_after_preview(self):
        outline = self.preprod()
        self.promote(self.prepare(outline))
        prod = self.prod()
        package = self.prepare(outline, "test-2")
        chunk = self.source()
        self.assign(chunk, prod)
        # Assignments are edited separately and do not bump the outline revision.
        self.assertEqual(self.prod()["revision"], prod["revision"])
        with self.assertRaises(app.Conflict):
            self.promote(package)
        self.assertEqual(self.store.releases.listing()["active"]["version"], "test-1")
        self.assertEqual(len(self.store.sources.chunks(chunk["source_id"])[0]["assignments"]), 1)

    def test_rollback_rejects_prod_assignment_edits_and_preserves_them(self):
        package = self.promote(self.prepare(self.preprod()))
        prod = self.prod()
        chunk = self.source()
        self.assign(chunk, prod)
        with self.assertRaises(app.Conflict):
            self.store.releases.rollback(dict(id=package["id"], revision=package["revision"],
                                             acknowledged=True, note="Fachliche Rücknahme."))
        self.assertEqual(self.prod()["revision"], prod["revision"])
        self.assertEqual(len(self.store.sources.chunks(chunk["source_id"])[0]["assignments"]), 1)

    def test_concurrent_question_cannot_overwrite_chat_history(self):
        entry = self.faq()
        session = self.ask()
        def concurrent_answer(*args):
            self.ask(id=session["id"], revision=session["revision"])
            return {"selections": [{"id": entry["id"], "quote": entry["answer"]}]}
        with patch("local_model.ask", side_effect=concurrent_answer):
            with self.assertRaises(app.Conflict):
                self.ask(id=session["id"], revision=session["revision"], mode="ollama", model="mock")
        result = self.store.chat.get(session["id"])
        self.assertEqual(result["revision"], 2)
        self.assertEqual(len(result["turns"]), 2)

    def test_model_cannot_cite_unsubmitted_faq_even_with_valid_quote(self):
        self.faq()
        other = self.store.internal.save(dict(id=app.uid(), revision=0, title="Getrennte FAQ",
            question="Welche Vertragsdauer gilt?", answer="Geheim im anderen Markt.",
            categories=["internal-testing"], status="Freigegeben", chatbot_enabled=True,
            roles=["HQ"], markets=["FR"]))
        with patch("local_model.ask", return_value={"selections": [{"id": other["id"], "quote": other["answer"]}]}) as model:
            with self.assertRaises(app.Invalid):
                self.ask(mode="ollama", model="mock")
        sent = model.call_args.args[2]["evidence"]
        self.assertNotIn(other["id"], [row["id"] for row in sent])
        self.assertEqual(self.store.chat.listing(), [])

    def test_model_cannot_remove_negation_by_selecting_answer_fragment(self):
        entry = self.faq(answer="Die Vertragsdauer beträgt nicht zwölf Monate.")
        with patch("local_model.ask", return_value={"selections": [{"id": entry["id"], "quote": "zwölf Monate."}]}):
            try:
                result = self.ask(mode="ollama", model="mock")
            except app.Invalid:
                # Rejecting incomplete evidence is as safe as displaying full context.
                self.assertEqual(self.store.chat.listing(), [])
                return
        turn = result["turns"][0]
        self.assertIn(entry["answer"], turn["answer"])
        self.assertIn(entry["answer"], turn["citations"][0]["quote"])

    def test_new_conflicting_faq_marks_prior_answer_outdated(self):
        self.faq()
        chat = self.ask()
        self.faq(answer="Die Vertragsdauer beträgt vierundzwanzig Monate.")
        self.assertEqual(self.ask()["turns"][0]["status"], "widersprüchlich")
        historical = self.store.chat.get(chat["id"])["turns"][0]
        self.assertTrue(historical["stale"])
        # Preserve the recorded original answer; do not rewrite conversation history.
        self.assertEqual(historical["answer"], chat["turns"][0]["answer"])

    def test_context_change_during_ai_review_invalidates_result(self):
        left = self.source("links.txt", "Der Vertrag gilt zwölf Monate.")
        right = self.source("rechts.txt", "Der Vertrag gilt vierundzwanzig Monate.")
        def inspect(*args):
            self.store.review.save_context(dict(id=left["source_id"], revision=0, market="FR"))
            return dict(reason="Abweichende Dauer", left_quote=left["text"], right_quote=right["text"])
        with patch("local_model.ask", side_effect=inspect):
            with self.assertRaises(app.Conflict):
                self.store.review.inspect(dict(left_id=left["id"], right_id=right["id"], mode="ollama", model="mock"))
        self.assertEqual(self.store.review.listing(), [])

    def test_context_dimensions_keep_distinct_sources_separate(self):
        dimensions = [("market", "DE", "FR"), ("role", "HQ", "Retailer"),
                      ("division", "Van", "PC"), ("language", "de", "en"),
                      ("environment", "prod", "preprod")]
        for key, a, b in dimensions:
            with self.subTest(dimension=key):
                left = self.source(key + "-links.txt", key + ": Der Vertrag gilt 12 Monate.")
                right = self.source(key + "-rechts.txt", key + ": Der Vertrag gilt 24 Monate.")
                for chunk, value in [(left, a), (right, b)]:
                    self.store.review.save_context(dict(id=chunk["source_id"], revision=0, **{key: value}))
                scan = self.store.review.scan({"sources": [left["source_id"], right["source_id"]]})
                self.assertEqual(scan["reviews"], [])
                self.assertEqual(scan["separated"], 1)
                with self.assertRaises(app.Invalid):
                    self.store.review.inspect(dict(left_id=left["id"], right_id=right["id"], reason="Manuell vergleichen"))

    def test_restored_overlap_reopens_retired_review(self):
        outline = self.preprod()
        left = self.source("alt.txt", "Der Vertrag gilt 12 Monate.")
        right = self.source("neu.txt", "Der Vertrag gilt 24 Monate.")
        self.assign(left, outline)
        self.store.review.scan({"sources": [left["source_id"], right["source_id"]]})
        review = self.store.review.listing()[0]
        self.store.review.save_context(dict(id=left["source_id"], revision=0, market="DE"))
        self.store.review.save_context(dict(id=right["source_id"], revision=0, market="FR"))
        self.store.review.decide(dict(id=review["id"], revision=review["revision"],
                                     status="Nicht mehr anwendbar", decision="Getrennte Märkte."))
        self.assertEqual(self.prepare(outline)["blockers"], [])
        self.store.review.save_context(dict(id=right["source_id"], revision=1, market="DE"))
        review = self.store.review.listing()[0]
        self.assertTrue(review["stale"])
        self.assertEqual(review["effective_status"], "Erneut prüfen")
        self.assertTrue(any("Quellenprüfung" in b for b in self.prepare(outline)["blockers"]))
