import json
import unittest

from helpers import CH01_HTML, AppCase
from services import claim_service as cs
from services import conflict_service

ROLES = ["Dealer", "Market Operations"]
SYSTEMS = ["Jira", "Confluence"]


def make(statement, cid=None, **overrides):
    analysis = cs.analyse_statement(statement, ROLES, SYSTEMS)
    claim = {"claimId": cid or f"CLM-{abs(hash(statement)) % 10**8:08d}", "chapterId": "CH01", "questionId": "01-F04",
             "knowledgeId": "KB-X", "canonicalStatement": statement, "criticality": "HIGH",
             "validationStatus": "DRAFT", **analysis}
    claim.update(overrides)
    return claim


def types(*claims):
    return sorted(c["type"] for c in conflict_service.detect("CH01", list(claims)))


class ClaimRuleTests(unittest.TestCase):
    def test_conjunction_split_only_when_distinct(self):
        self.assertEqual(len(cs.split_conjunctions("Der Dealer erstellt Aufträge und Market Operations genehmigt Preise.", ROLES)), 2)
        self.assertEqual(len(cs.split_conjunctions("Der Dealer erstellt Aufträge und Angebote.", ROLES)), 1)
        self.assertEqual(len(cs.split_conjunctions("Die Funktion ist in PI16 umgesetzt und in PI17 für VAN geplant.", ROLES)), 2)

    def test_conditions_are_not_split(self):
        statement = "Wenn der Auftrag offen ist, darf der Dealer stornieren und Market Operations genehmigt die Gutschrift."
        self.assertEqual(cs.split_conjunctions(statement, ROLES), [statement])
        self.assertTrue(cs.analyse_statement(statement, ROLES, SYSTEMS)["conditional"])

    def test_negation_uncertainty_pi_maturity(self):
        a = cs.analyse_statement("Der Dealer darf Aufträge nicht stornieren.", ROLES, SYSTEMS)
        self.assertTrue(a["negated"])
        self.assertEqual(a["role"], "Dealer")
        self.assertEqual(a["predicate"], "stornieren")
        self.assertEqual(a["claimType"], "PERMISSION")
        self.assertIn("irreversible", a["tags"])
        b = cs.analyse_statement("Die Erweiterung ist möglicherweise ab PI17 verfügbar.", ROLES, SYSTEMS)
        self.assertTrue(b["uncertain"])
        self.assertEqual(b["pi"], 17)
        self.assertEqual(b["claimType"], "PLAN")
        for text, expected in [("Die Funktion ist im Test.", "IN_TEST"), ("Die Funktion ist abgenommen.", "ACCEPTED"),
                               ("Die Funktion ist umgesetzt und produktiv.", "IMPLEMENTED"),
                               ("Die Funktion ist seit PI16 produktiv.", "PRODUCTION"), ("Die Funktion ist nicht produktiv.", "")]:
            self.assertEqual(cs.analyse_statement(text, ROLES, SYSTEMS)["maturity"], expected, text)
        self.assertEqual(cs.analyse_statement("Funktion für PC und VAN.", ROLES, SYSTEMS)["division"], "BOTH")
        self.assertEqual(cs.analyse_statement("Funktion nur für VAN.", ROLES, SYSTEMS)["division"], "VAN")
        self.assertEqual(cs.analyse_statement("Preise gelten im Markt Deutschland.", ROLES, SYSTEMS)["market"], "Deutschland")
        self.assertIn("financial", cs.analyse_statement("Preise gelten im Markt Deutschland.", ROLES, SYSTEMS)["tags"])


class ConflictTests(unittest.TestCase):
    def test_direct_contradiction(self):
        self.assertEqual(types(make("Der Dealer darf Aufträge stornieren."), make("Der Dealer darf Aufträge nicht stornieren.")),
                         ["DIRECT_CONTRADICTION"])

    def test_different_scope_is_not_a_conflict(self):
        self.assertEqual(types(make("Der Dealer darf für PC Aufträge stornieren."), make("Der Dealer darf für VAN Aufträge nicht stornieren.")), [])
        self.assertEqual(types(make("Der Dealer darf Aufträge stornieren."), make("Wenn die Rechnung gebucht ist, darf der Dealer Aufträge nicht stornieren.")), [])

    def test_rejected_claims_ignored(self):
        self.assertEqual(types(make("Der Dealer darf Aufträge stornieren."), make("Der Dealer darf Aufträge nicht stornieren.", validationStatus="REJECTED")), [])

    def test_maturity_and_pi_conflicts(self):
        self.assertEqual(types(make("Die Auftragsfreigabe ist in PI16 produktiv."), make("Die Auftragsfreigabe ist in PI16 im Test.")), ["MATURITY_CONFLICT"])
        self.assertEqual(types(make("Die Auftragsfreigabe ist in PI16 produktiv."), make("Die Auftragsfreigabe ist in PI17 produktiv.")), ["PI_CONFLICT"])

    def test_role_division_and_source_system_conflicts(self):
        found = conflict_service.detect("CH01", [make("Der Dealer genehmigt Preisänderungen.", criticality="CRITICAL"),
                                                  make("Market Operations genehmigt Preisänderungen.")])
        self.assertEqual([(c["type"], c["severity"]) for c in found], [("ROLE_CONFLICT", "CRITICAL")])
        self.assertEqual(types(make("Die Exportfunktion ist für PC und VAN verfügbar."), make("Die Exportfunktion ist nur für PC verfügbar.")),
                         ["DIVISION_CONFLICT"])
        self.assertEqual(types(make("Jira ist datenführend für die Releaseplanung."), make("Confluence ist datenführend für die Releaseplanung.")),
                         ["SOURCE_SYSTEM_CONFLICT"])

    def test_conflict_key_is_stable(self):
        a, b = make("Der Dealer darf Aufträge stornieren.", "CLM-A"), make("Der Dealer darf Aufträge nicht stornieren.", "CLM-B")
        self.assertEqual(conflict_service.detect("CH01", [a, b])[0]["key"], conflict_service.detect("CH01", [b, a])[0]["key"])


class ClaimApiTests(AppCase, unittest.TestCase):
    def _manual(self, text, question="01-F04"):
        r = self.post("/api/claims", {"chapterId": "CH01", "questionId": question, "canonicalStatement": text})
        self.assertEqual(r.status_code, 201, r.get_json())
        return r.get_json()

    def test_import_creates_draft_claims_and_evidence(self):
        self.upload(CH01_HTML, "ch01.html")
        claims = self.client.get("/api/claims?chapterId=CH01").get_json()
        self.assertTrue(all(c["validationStatus"] == "DRAFT" for c in claims))
        statements = [c["canonicalStatement"] for c in claims]
        self.assertIn("oneSCM unterstützt den Dealer bei Aufträgen für PC und VAN.", statements)
        evidence = self.client.get("/api/evidence").get_json()
        rovo = [e for e in evidence if e["sourceType"] == "ROVO"]
        self.assertTrue(rovo and all(e["evidenceStrength"] == "INDIRECT" for e in rovo))
        jira = [e for e in evidence if e["sourceType"] == "JIRA"]
        self.assertEqual([e["jiraKey"] for e in jira], ["ONESCM-123"])
        self.assertEqual(jira[0]["evidenceStrength"], "DIRECT")
        blocks = self.client.get("/api/knowledge-blocks").get_json()
        self.assertTrue({c["knowledgeId"] for c in claims} <= {b["knowledgeId"] for b in blocks})
        uncertain = next(c for c in claims if "möglicherweise" in c["canonicalStatement"])
        self.assertTrue(uncertain["uncertain"])
        r = self.put(f"/api/claims/{uncertain['claimId']}", {"validationStatus": "CONFIRMED"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("Unsichere", r.get_json()["error"])

    def test_claim_crud_and_validation(self):
        claim = self._manual("Der Dealer darf Aufträge erstellen.")
        self.assertEqual(claim["evidenceStatus"], "NOT_EVIDENCED")
        self.assertEqual(claim["criticality"], "CRITICAL")
        self.assertEqual(self.post("/api/claims", {"chapterId": "CH01", "questionId": "02-F01", "canonicalStatement": "x y z"}).status_code, 400)
        self.assertEqual(self.post("/api/claims", {"chapterId": "CH01", "questionId": "01-F01", "canonicalStatement": " "}).status_code, 400)
        r = self.put(f"/api/claims/{claim['claimId']}", {"role": "Market Operations", "pi": "16", "maturity": "PRODUCTION", "division": "PC"})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(r.get_json()["pi"], 16)
        self.assertEqual(self.put(f"/api/claims/{claim['claimId']}", {"maturity": "LIVE"}).status_code, 400)
        self.assertEqual(self.put(f"/api/claims/{claim['claimId']}", {"evidenceStatus": "NOT_RELEVANT"}).status_code, 400)
        self.assertEqual(self.put(f"/api/claims/{claim['claimId']}", {"questionId": "01-F05"}).status_code, 400)  # KB belongs to F04
        self.assertEqual(self.delete(f"/api/claims/{claim['claimId']}").status_code, 200)
        self.assertEqual(self.delete(f"/api/claims/{claim['claimId']}").status_code, 404)

    def test_evidence_crud_and_rules(self):
        claim = self._manual("Der Dealer darf Aufträge erstellen.")
        self.assertEqual(self.post("/api/evidence", {"claimId": "CLM-NOPE"}).status_code, 400)
        self.assertEqual(self.post("/api/evidence", {"claimId": claim["claimId"], "sourceType": "JIRA", "jiraKey": "abc"}).status_code, 400)
        self.assertEqual(self.post("/api/evidence", {"claimId": claim["claimId"], "sourceURL": "javascript:alert(1)"}).status_code, 400)
        self.assertEqual(self.post("/api/evidence", {"claimId": claim["claimId"], "evidenceStrength": "DIRECT_VALIDATED"}).status_code, 400)
        ev = self.post("/api/evidence", {"claimId": claim["claimId"], "sourceType": "JIRA", "jiraKey": "ONESCM-7",
                                         "evidenceStrength": "DIRECT"}).get_json()
        claims = self.client.get("/api/claims").get_json()
        self.assertEqual(claims[0]["evidenceStatus"], "EVIDENCED")
        self.assertAlmostEqual(claims[0]["evidenceFactor"], 0.9)
        r = self.put(f"/api/evidence/{ev['evidenceId']}", {"evidenceStrength": "DIRECT_VALIDATED", "evidenceStatus": "VALIDATED"})
        self.assertEqual(r.status_code, 200)
        self.assertAlmostEqual(self.client.get("/api/claims").get_json()[0]["evidenceFactor"], 1.0)
        self.assertEqual(self.put(f"/api/claims/{claim['claimId']}", {"evidenceStatus": "NOT_RELEVANT"}).status_code, 200)
        self.assertEqual(self.delete(f"/api/evidence/{ev['evidenceId']}").status_code, 200)
        self.assertEqual(self.client.get("/api/claims").get_json()[0]["evidenceStatus"], "NOT_EVIDENCED")

    def test_conflict_resolution_lifts_blocker(self):
        a = self._manual("Der Dealer darf Aufträge stornieren.")
        self._manual("Der Dealer darf Aufträge nicht stornieren.")
        cov = self.client.get("/api/coverage/CH01").get_json()
        self.assertTrue(any("Offener kritischer Konflikt" in b for b in cov["blockers"]))
        conflict = self.client.get("/api/conflicts?chapterId=CH01").get_json()[0]
        self.assertEqual(conflict["type"], "DIRECT_CONTRADICTION")
        self.assertEqual(self.put(f"/api/conflicts/{conflict['conflictId']}", {"status": "RESOLVED"}).status_code, 400)
        self.assertEqual(self.put(f"/api/conflicts/{conflict['conflictId']}", {"status": "RESOLVED", "resolutionNote": "Stornierung nur vor Auslieferung"}).status_code, 200)
        cov = self.client.get("/api/coverage/CH01").get_json()
        self.assertFalse(any("Konflikt" in b for b in cov["blockers"]))
        # Status survives re-detection; deleting a claim removes its conflicts.
        self.assertEqual(self.client.get("/api/conflicts").get_json()[0]["status"], "RESOLVED")
        self.delete(f"/api/claims/{a['claimId']}")
        self.assertEqual(self.client.get("/api/conflicts").get_json(), [])

    def test_orphaned_evidence_blocks(self):
        self._manual("Der Dealer darf Aufträge erstellen.")
        path = self.tmp / "data" / "knowledge.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["evidence"].append({"evidenceId": "EVD-ORPHAN", "claimId": "CLM-GONE", "sourceType": "JIRA", "evidenceStrength": "DIRECT", "evidenceStatus": "PROPOSED"})
        path.write_text(json.dumps(data), encoding="utf-8")
        cov = self.client.get("/api/coverage/CH01").get_json()
        self.assertEqual(cov["gate"], "BLOCKED")
        self.assertTrue(any("Referentielle Integrität" in b and "EVD-ORPHAN" in b for b in cov["blockers"]))
        self.assertTrue(self.client.get("/api/integrity").get_json()["problems"])


if __name__ == "__main__":
    unittest.main()
