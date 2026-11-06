import json
import unittest

from helpers import AppCase, html_doc, p
from services.rule_service import RuleService


class RuleTests(AppCase, unittest.TestCase):
    def test_crud_persistence_and_backup(self):
        r = self.post("/api/rules", {"category": "abbreviation", "source": "VAN", "target": "Vans / Transporter"})
        self.assertEqual(r.status_code, 201, r.get_json())
        rule = r.get_json()
        self.assertRegex(rule["id"], r"^R-\d{4}$")
        stored = json.loads(self.rules_path.read_text(encoding="utf-8"))
        self.assertIn(rule["id"], [x["id"] for x in stored["rules"]])
        # A fresh service instance (= after restart) sees the same rules.
        fresh = RuleService(self.rules_path, self.tmp / "b")
        self.assertIn(rule["id"], [x["id"] for x in fresh.list()])
        r = self.put(f"/api/rules/{rule['id']}", {"category": "abbreviation", "source": "VAN", "target": "Van Division", "note": "geändert"})
        self.assertEqual(r.get_json()["target"], "Van Division")
        self.assertEqual(self.delete(f"/api/rules/{rule['id']}").status_code, 200)
        self.assertNotIn(rule["id"], [x["id"] for x in self.client.get("/api/rules").get_json()])
        self.assertEqual(self.delete(f"/api/rules/{rule['id']}").status_code, 404)
        backups = list((self.tmp / "data" / "backups").glob("rules-*.json"))
        self.assertGreaterEqual(len(backups), 3)

    def test_validation_and_duplicates(self):
        self.assertEqual(self.post("/api/rules", {"category": "naming", "source": "ONESCM", "target": "oneSCM"}).status_code, 409)
        self.assertEqual(self.post("/api/rules", {"category": "unknown", "source": "a", "target": "b"}).status_code, 400)
        self.assertEqual(self.post("/api/rules", {"category": "synonym", "source": "  ", "target": "b"}).status_code, 400)
        self.assertEqual(self.post("/api/rules", {"category": "synonym", "source": "Pkw", "target": ""}).status_code, 400)
        self.assertEqual(self.post("/api/rules", {"category": "synonym", "source": "Pkw", "target": "Pkw"}).status_code, 400)
        system = self.post("/api/rules", {"category": "system", "source": "SAP", "target": "ignored"}).get_json()
        self.assertEqual(system["target"], "")
        other = self.post("/api/rules", {"category": "system", "source": "Salesforce"}).get_json()
        self.assertEqual(self.put(f"/api/rules/{other['id']}", {"category": "system", "source": "sap"}).status_code, 409)

    def test_rules_apply_immediately_without_restart(self):
        doc = html_doc(p("F01 Der Händler nutzt das Fahrzeugportal für Bestellungen."))
        rec = self.upload(doc, "a.html").get_json()["importRecord"]
        self.assertEqual(rec["findings"], [])
        self.post("/api/rules", {"category": "synonym", "source": "Händler", "target": "Dealer"})
        rec = self.upload(doc, "a.html", force=True).get_json()["importRecord"]
        question = rec["questions"][0]
        self.assertIn("Händler", question["text"])  # raw text never overwritten
        self.assertIn("Dealer", question["normalizedText"])
        self.assertEqual(rec["findings"][0]["category"], "synonym")

    def test_rule_application_details(self):
        rules = self.services()["rules"]
        text = "Im onescm (siehe ONESCM-42) prüft der Dealer die Eligibility für Passenger Cars ab PI16 in Jira."
        normalized, findings = rules.apply(text)
        self.assertIn("oneSCM (siehe ONESCM-42)", normalized)
        self.assertIn("Passenger Cars", normalized)  # no partial-word match
        categories = {f["category"] for f in findings}
        self.assertEqual(categories, {"naming", "explanation", "abbreviation", "system"})
        preview = self.post("/api/rules/preview", {"text": "Passenger Car und onescm"}).get_json()
        self.assertEqual(preview["normalizedText"], "PC und oneSCM")

    def test_corrupt_rules_file_reported(self):
        self.rules_path.write_text("{kaputt", encoding="utf-8")
        r = self.client.get("/api/rules")
        self.assertEqual(r.status_code, 500)
        self.assertIn("beschädigt", r.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
