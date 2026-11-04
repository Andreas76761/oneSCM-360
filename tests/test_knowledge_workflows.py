"""Integration tests for cited internal answers, review and atomic documentation releases."""
import copy
from datetime import date, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import app
import knowledge_review


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = app.Store(Path(self.temp.name) / "workflow.sqlite3")
        self.today = date.today().isoformat()
        self.profile = {"role":"HQ", "market":"DE", "language":"de", "division":"PC", "as_of":self.today, "environment":"prod"}

    def tearDown(self):
        self.temp.cleanup()

    def faq(self, **extra):
        return self.store.internal.save({"id":app.uid(), "revision":0, "title":"Testvertrag Laufzeit", "question":"Welche Laufzeit hat der Testvertrag?",
            "answer":"Der Testvertrag hat eine Laufzeit von 12 Monaten.", "body":"PRIVATE_BODY_NOT_EVIDENCE", "note":"PRIVATE_NOTE_NOT_EVIDENCE",
            "categories":["internal-testing"], "status":"Freigegeben", "roles":["HQ"], "markets":["DE"], "source":"Confluence Export · Kapitel 3 · SCM-12", "chatbot_enabled":True, **extra})

    def ask(self, **extra):
        return self.store.chat.ask({"question":"Welche Laufzeit hat der Testvertrag?", "profile":self.profile, **extra})

    def preprod(self, market="DE", version="2026.11", text="Der Händler öffnet den Vertrag."):
        o = app.new_outline("Handbuch " + market)
        o["profile"].update(market=market, environment="preprod", as_of=self.today, release=version)
        o["chapters"] = [app.chapter("Vertrag", mandatory=True)]
        o["chapters"][0]["config"] = {"status":"Freigegeben"}
        o["chapters"][0]["blocks"] = [dict(app.block(), text=text, status="Freigegeben")]
        return self.store.save(self.store.save(o), releasing=True)

    def prepare(self, *outlines, **extra):
        return self.store.releases.prepare({"sources":[o["id"] for o in outlines], "version":"2026.11", "date":self.today, **extra})

    def promote(self, package):
        return self.store.releases.promote({"id":package["id"], "revision":package["revision"], "acknowledged":True, "note":"Quellen, Änderungen und alle Profile geprüft."})

    def rollback(self, package):
        return self.store.releases.rollback({"id":package["id"], "revision":package["revision"], "acknowledged":True, "note":"Fachliche Rücknahme zum vorherigen Stand."})

    def sources(self):
        a = self.store.sources.upload("old.html", b"<p>Der Testvertrag hat eine Laufzeit von 12 Monaten.</p>", {"kind":"Confluence", "release":"2026.10"})
        b = self.store.sources.upload("new.html", b"<p>Der Testvertrag hat eine Laufzeit von 24 Monaten.</p>", {"kind":"Jira", "release":"2026.11"})
        return a, b

    def link(self, source, outline):
        chunk = self.store.sources.chunks(source["id"])[0]
        self.store.sources.review({"id":chunk["id"], "revision":chunk["revision"], "labels":{}, "assignments":[{"outline_id":outline["id"],"chapter_id":outline["chapters"][0]["id"]}]}, set())

    def test_chat_quotes_real_revision_and_excludes_private_body(self):
        entry = self.faq()
        result = self.ask()
        turn = result["turns"][0]
        self.assertEqual(turn["status"], "belegt")
        self.assertIn(entry["answer"], turn["answer"])
        cite = turn["citations"][0]
        self.assertEqual(cite["id"], entry["id"])
        self.assertEqual(cite["revision"], 1)
        self.assertIn("SCM-12", cite["source"])
        self.assertNotIn("PRIVATE_BODY", json.dumps(result))
        self.assertNotIn("PRIVATE_NOTE", json.dumps(result))
        self.assertNotIn(entry["answer"], json.dumps(self.store.all()))

    def test_chat_filters_before_model_and_refuses_missing_evidence(self):
        self.faq(status="Entwurf")
        self.faq(roles=["Retailer"])
        self.faq(markets=["FR"])
        self.faq(language="en")
        self.faq(divisions=["Van"])
        self.faq(validity=[{"environment":"preprod", "state":"Freigegeben"}])
        self.faq(chatbot_enabled=False)
        with patch("local_model.ask") as model:
            result = self.ask(mode="ollama", model="local")
            self.assertEqual(result["turns"][0]["status"], "keine_belege")
            model.assert_not_called()

    def test_chat_conflict_refuses_single_answer(self):
        self.faq()
        self.faq(answer="Der Testvertrag hat eine Laufzeit von 24 Monaten.")
        result = self.ask()["turns"][0]
        self.assertEqual(result["status"], "widersprüchlich")
        self.assertEqual(len(result["citations"]), 2)
        self.assertIn("Keine eindeutige Antwort", result["answer"])

    def test_chat_rechecks_citations_and_profile_bound_history(self):
        entry = self.faq()
        chat = self.ask()
        entry["status"] = "Archiviert"
        self.store.internal.save(entry)
        self.assertTrue(self.store.chat.get(chat["id"])["turns"][0]["stale"])
        new = self.ask(id=chat["id"], revision=chat["revision"], followup=True)
        self.assertEqual(new["turns"][-1]["status"], "keine_belege")
        with self.assertRaises(app.Conflict):
            self.ask(id=new["id"], revision=new["revision"], profile={**self.profile,"market":"FR"})

    def test_model_quote_validation_and_no_silent_fallback(self):
        entry = self.faq()
        with patch("local_model.ask", return_value={"selections":[{"id":entry["id"], "quote":"Erfundene Antwort."}]}):
            with self.assertRaises(app.Invalid): self.ask(mode="ollama", model="local")
        self.assertEqual(self.store.chat.listing(), [])
        with patch("local_model.ask", return_value={"selections":[{"id":entry["id"], "quote":entry["answer"]}]}) as model:
            self.assertEqual(self.ask(mode="ollama", model="local")["turns"][0]["status"], "belegt")
            payload = json.dumps(model.call_args.args)
            self.assertNotIn("PRIVATE_BODY", payload)
            self.assertNotIn("PRIVATE_NOTE", payload)

    def test_model_race_rechecks_faq_before_storing_answer(self):
        entry = self.faq()
        def generate(*args):
            self.store.internal.save({**entry, "status":"Archiviert"})
            return {"selections":[{"id":entry["id"], "quote":entry["answer"]}]}
        with patch("local_model.ask", side_effect=generate):
            with self.assertRaises(app.Conflict):self.ask(mode="ollama", model="local")
        self.assertEqual(self.store.chat.listing(), [])

    def test_rule_scan_numbers_negation_duplicates_and_context(self):
        a, b = self.sources()
        scan = self.store.review.scan({"sources":[a["id"], b["id"]]})
        self.assertEqual(len(scan["reviews"]), 1)
        row = self.store.review.listing()[0]
        self.assertIn("Versionsänderung", row["reason"])
        self.assertEqual(row["status"], "Offen")
        self.assertIn("12 Monaten", row["left_quote"])
        self.assertIn("24 Monaten", row["right_quote"])
        self.assertTrue(knowledge_review.signals("Der Händler darf den Vertrag bearbeiten.", "Der Händler darf den Vertrag nicht bearbeiten."))
        self.assertEqual(knowledge_review.signals("Vertrag öffnen", "Vertrag öffnen.")["kind"], "Duplikat")
        self.store.review.save_context({"id":a["id"], "revision":0, "market":"DE"})
        self.store.review.save_context({"id":b["id"], "revision":0, "market":"FR"})
        self.assertFalse(self.store.review.scan({"sources":[a["id"],b["id"]]})["reviews"])

    def test_decision_history_staleness_and_rescan_replacement(self):
        a,b = self.sources()
        self.store.review.scan({"sources":[a["id"],b["id"]]})
        row = self.store.review.listing()[0]
        decided = self.store.review.decide({"id":row["id"], "revision":1, "status":"Geklärt", "decision":"Neues Release ersetzt alten Stand.", "preferred":"right"})
        self.assertEqual(len(self.store.review.history(row["id"])), 2)
        self.store.review.save_context({"id":a["id"], "revision":0, "date":self.today})
        self.assertTrue(self.store.review.listing()[0]["stale"])
        with self.assertRaises(app.Conflict):self.store.review.decide({"id":row["id"], "revision":decided["revision"], "status":"Geklärt", "decision":"stale"})
        self.store.review.scan({"sources":[a["id"],b["id"]]})
        rows = self.store.review.listing()
        self.assertFalse(rows[0]["stale"])
        self.assertEqual(rows[1]["superseded_by"], rows[0]["id"])

    def test_ai_conflict_requires_literal_quotes_and_keeps_sources_unchanged(self):
        a,b = self.sources();left,right = self.store.sources.chunks(a["id"])[0],self.store.sources.chunks(b["id"])[0]
        data = {"left_id":left["id"],"right_id":right["id"],"mode":"ollama","model":"local"}
        with patch("local_model.ask", return_value={"reason":"Werte weichen ab", "left_quote":"erfunden", "right_quote":right["text"]}):
            with self.assertRaises(app.Invalid):self.store.review.inspect(data)
        self.assertFalse(self.store.review.listing())
        with patch("local_model.ask", return_value={"reason":"Werte weichen ab", "left_quote":left["text"], "right_quote":right["text"]}):
            row = self.store.review.inspect(data)
        self.assertEqual(row["status"], "Offen")
        self.assertEqual(self.store.sources.chunks(a["id"])[0],left)

    def test_promotion_is_explicit_atomic_and_keeps_preprod(self):
        one,two = self.preprod("DE"),self.preprod("FR")
        package = self.prepare(one,two)
        self.assertEqual(package["blockers"], [])
        with self.assertRaises(app.Invalid):self.store.releases.promote({"id":package["id"], "revision":package["revision"]})
        self.assertEqual(len(self.store.all()), 2)
        promoted = self.promote(package)
        self.assertEqual(promoted["status"], "Aktiviert")
        active = self.store.releases.listing()["active"]
        self.assertEqual(len(active["members"]), 2)
        for member in active["members"]:
            prod = self.store.get(member["outline_id"])
            self.assertEqual(prod["profile"]["environment"], "prod")
            self.assertEqual(prod["metadata"]["status"], "Freigegeben")
            self.assertEqual(prod["profile"]["release"], "2026.11")
        self.assertEqual(self.store.get(one["id"]),one)
        with self.assertRaises(app.Conflict):self.promote(package)

    def test_failed_second_write_rolls_back_whole_package(self):
        one,two = self.preprod("DE"),self.preprod("FR")
        package = self.prepare(one,two);real_save = self.store.save;calls = []
        def save(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:raise app.Invalid("Injected failure")
            return real_save(*args, **kwargs)
        with patch.object(self.store,"save",side_effect=save):
            with self.assertRaises(app.Invalid):self.promote(package)
        self.assertEqual(len(self.store.all()),2)
        self.assertFalse(self.store.releases.listing()["active"]["members"])

    def test_source_changes_conflicts_and_missing_profiles_block_promotion(self):
        one,two = self.preprod("DE"),self.preprod("FR")
        package = self.prepare(one,two)
        changed = copy.deepcopy(one);changed["title"] = "Edited"
        one = self.store.save(self.store.save(changed), releasing=True)
        with self.assertRaises(app.Conflict):self.promote(package)
        a,b = self.sources();self.link(a,one);self.link(b,one)
        self.store.review.scan({"sources":[a["id"],b["id"]]})
        package = self.prepare(one,two)
        self.assertTrue(any("Quellenprüfung" in error for error in package["blockers"]))
        with self.assertRaises(app.Invalid):self.promote(package)
        review = self.store.review.listing()[0]
        self.store.review.decide({"id":review["id"],"revision":review["revision"],"status":"Geklärt","decision":"Neue Version gilt, Manuskript fachlich abgeglichen.","preferred":"right"})
        self.promote(self.prepare(one,two))
        missing = self.prepare(one, version="2026.12")
        self.assertTrue(any("Prod-Profil fehlt" in e for e in missing["blockers"]))

    def test_rollback_preserves_history_and_restores_previous_active_release(self):
        one = self.preprod();first = self.promote(self.prepare(one))
        before = self.store.releases.listing()["active"]
        prod_id = before["members"][0]["outline_id"]
        original = self.store.get(prod_id)
        one["chapters"][0]["blocks"][0]["text"] = "Neue Anleitung"
        one = self.store.save(self.store.save(one),releasing=True)
        second = self.promote(self.prepare(one,version="2026.12"))
        self.rollback(second)
        active = self.store.releases.listing()["active"]
        self.assertEqual(active["version"],"2026.11")
        restored = self.store.get(prod_id)
        self.assertEqual(restored["chapters"],original["chapters"])
        self.assertEqual(restored["revision"],3)
        self.assertEqual(len(self.store.history(prod_id)),3)
        self.rollback(first)
        self.assertFalse(self.store.releases.listing()["active"]["members"])
        self.assertEqual(self.store.get(prod_id)["metadata"]["status"],"Archiviert")

    def test_rollback_never_overwrites_later_edits(self):
        package = self.promote(self.prepare(self.preprod()))
        oid = self.store.releases.listing()["active"]["members"][0]["outline_id"]
        prod = self.store.get(oid);prod["title"] = "Later change";self.store.save(prod)
        with self.assertRaises(app.Conflict):self.rollback(package)
        self.assertEqual(self.store.get(oid)["title"],"Later change")

    def test_draft_future_and_preprod_only_rules_block(self):
        source = self.preprod()
        source["chapters"][0]["validity"] = [{"environment":"preprod","state":"Freigegeben"}]
        source = self.store.save(self.store.save(source),releasing=True)
        blocked = self.prepare(source)
        self.assertTrue(blocked["blockers"])
        with self.assertRaises(app.Invalid):self.promote(blocked)
        source = self.preprod("FR")
        planned = self.prepare(source,date=(date.today()+timedelta(days=2)).isoformat())
        with self.assertRaises(app.Invalid):self.promote(planned)

    def test_reversed_scan_and_new_prod_assignment_keep_review_decision(self):
        source = self.preprod();a,b = self.sources();self.link(a,source);self.link(b,source)
        self.store.review.scan({"sources":[a["id"],b["id"]]})
        row = self.store.review.listing()[0]
        self.store.review.decide({"id":row["id"],"revision":row["revision"],"status":"Geklärt","decision":"Versionsänderung mit Text abgeglichen."})
        self.store.review.scan({"sources":[b["id"],a["id"]]})
        self.assertEqual(len(self.store.review.listing()),1)
        self.promote(self.prepare(source))
        review = self.store.review.listing()[0]
        self.assertFalse(review["stale"])
        self.assertEqual(review["status"],"Geklärt")
        self.assertEqual(len(review["affected"]),2)

    def test_deleted_source_can_be_retired_with_audited_reason(self):
        a,b = self.sources();self.store.review.scan({"sources":[a["id"],b["id"]]})
        row = self.store.review.listing()[0]
        data = {"id":row["id"],"revision":row["revision"],"status":"Nicht mehr anwendbar","decision":"Altquelle wurde aus der Wissensbasis entfernt."}
        with self.assertRaises(app.Invalid):self.store.review.decide(data)
        self.store.sources.delete(a["id"])
        retired = self.store.review.decide(data)
        self.assertFalse(retired["stale"])
        self.assertEqual(retired["effective_status"],"Nicht mehr anwendbar")
        self.assertEqual(len(self.store.review.history(row["id"])),2)

    def test_second_prepared_package_cannot_overwrite_first_activation(self):
        source = self.preprod()
        first = self.prepare(source)
        second = self.prepare(source,version="2026.12")
        self.promote(first)
        with self.assertRaises(app.Conflict):self.promote(second)
        self.assertEqual(self.store.releases.listing()["active"]["version"],"2026.11")
