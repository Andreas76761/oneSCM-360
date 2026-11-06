import json
import unittest
from pathlib import Path

from helpers import CH01_HTML, ROOT, AppCase
from services import coverage_service


def chapter():
    return json.loads((ROOT / "chapters" / "CH01.json").read_text(encoding="utf-8"))


def full_claims():
    """Synthetic, fully evidenced and confirmed chapter."""
    claims, evidence = [], []
    cfg = chapter()
    for i, q in enumerate(cfg["questions"]):
        role = cfg["roles"][i % 2]
        claim = {"claimId": f"CLM-{i:04d}", "knowledgeId": "KB-1", "chapterId": "CH01", "questionId": q["questionId"],
                 "canonicalStatement": f"{role} darf nur eigene Vorgänge {i} bearbeiten.", "claimType": "PERMISSION",
                 "subject": role, "predicate": "bearbeiten", "object": f"vorgang{i}", "negated": False,
                 "criticality": q["criticality"], "division": ["PC", "VAN", "BOTH"][i % 3], "role": role,
                 "pi": 16 if i % 2 == 0 else 17, "maturity": "PRODUCTION" if i % 2 == 0 else "PLANNED",
                 "tags": [], "validationStatus": "CONFIRMED", "evidenceStatus": "EVIDENCED"}
        claims.append(claim)
        evidence.append({"evidenceId": f"EVD-{i}", "claimId": claim["claimId"], "sourceType": "JIRA",
                         "evidenceStrength": "DIRECT_VALIDATED", "evidenceStatus": "VALIDATED"})
    return claims, evidence


class CoverageUnitTests(unittest.TestCase):
    def test_empty_is_not_started(self):
        cov = coverage_service.calculate(chapter(), [], [], [], [], {})
        self.assertEqual(cov["readiness"], 0)
        self.assertEqual(cov["gate"], "NOT_STARTED")

    def test_ready_when_everything_confirmed(self):
        claims, evidence = full_claims()
        cov = coverage_service.calculate(chapter(), claims, evidence, [], [], {})
        self.assertEqual(cov["readiness"], 100.0, cov)
        self.assertEqual(cov["gate"], "READY")
        self.assertEqual(cov["blockers"], [])

    def test_weights_and_formula(self):
        self.assertEqual(coverage_service.WEIGHTS, {"questions": 0.20, "evidence": 0.30, "roles": 0.15, "division": 0.15, "pi": 0.10, "confidence": 0.10})
        claims, evidence = full_claims()
        for ev in evidence:
            ev["evidenceStrength"], ev["evidenceStatus"] = "DIRECT", "PROPOSED"
        cov = coverage_service.calculate(chapter(), claims, evidence, [], [], {})
        expected = round((cov["questionCoverage"] * .2 + cov["evidenceCoverage"] * .3 + cov["roleCoverage"] * .15
                          + cov["divisionCoverage"] * .15 + cov["piCoverage"] * .1 + cov["confidence"] * .1), 1)
        self.assertAlmostEqual(cov["readiness"], expected, delta=0.15)
        self.assertEqual(cov["evidenceCoverage"], 90.0)
        self.assertEqual(cov["confidence"], 98.0)
        self.assertEqual(cov["readiness"], 96.8)
        self.assertEqual(cov["gate"], "READY")  # Evidence = 90 meets the ">= 90" threshold

    def test_critical_unevidenced_claim_blocks_regardless_of_score(self):
        claims, evidence = full_claims()
        critical = next(c for c in claims if c["criticality"] == "CRITICAL")
        for ev in evidence:
            if ev["claimId"] == critical["claimId"]:
                ev["evidenceStrength"] = "INDIRECT"
        cov = coverage_service.calculate(chapter(), claims, evidence, [], [], {})
        self.assertGreater(cov["readiness"], 90)
        self.assertEqual(cov["gate"], "BLOCKED")
        self.assertTrue(any("Kritischer Claim ohne direkte Evidence" in b for b in cov["blockers"]))

    def test_hard_blockers_for_tags_and_conflicts(self):
        claims, evidence = full_claims()
        claims[0]["tags"] = ["financial"]
        claims[0]["validationStatus"] = "REVIEWED"
        cov = coverage_service.calculate(chapter(), claims, evidence, [], [], {})
        self.assertTrue(any("finanzielle Regel" in b for b in cov["blockers"]))
        claims[0]["validationStatus"] = "CONFIRMED"
        conflict = {"conflictId": "CNF-1", "chapterId": "CH01", "type": "MATURITY_CONFLICT", "severity": "CRITICAL",
                    "claimIds": ["CLM-0000", "CLM-0002"], "status": "OPEN"}
        cov = coverage_service.calculate(chapter(), claims, evidence, [conflict], [], {})
        self.assertTrue(any("Widersprüchlicher Produktivstatus" in b for b in cov["blockers"]))
        major = dict(conflict, severity="MAJOR", type="PI_CONFLICT")
        cov = coverage_service.calculate(chapter(), claims, evidence, [major], [], {})
        self.assertEqual(cov["blockers"], [])
        self.assertEqual(cov["conflicts"], 1)

    def test_gate_thresholds(self):
        g = coverage_service._gate
        self.assertEqual(g(95, 95, True, True, ["x"])[0], "BLOCKED")
        self.assertEqual(g(90, 90, True, True, [])[0], "READY")
        self.assertEqual(g(95, 89.9, True, True, [])[0], "REVIEW")
        self.assertEqual(g(95, 95, False, True, [])[0], "REVIEW")
        self.assertEqual(g(70, 50, True, True, [])[0], "REVIEW")
        self.assertEqual(g(69.9, 50, True, True, [])[0], "INCOMPLETE")
        self.assertEqual(g(40, 50, True, True, [])[0], "INCOMPLETE")
        self.assertEqual(g(39.9, 50, True, True, [])[0], "STARTED")
        self.assertEqual(g(0, 0, True, True, [])[0], "NOT_STARTED")

    def test_pc_evidence_does_not_count_for_van(self):
        claims, evidence = full_claims()
        for c in claims:
            c["division"] = "PC"
        cov = coverage_service.calculate(chapter(), claims, evidence, [], [], {})
        self.assertEqual(cov["divisionCoverage"], 50.0)
        claims[0]["division"] = "VAN"
        evidence[0]["evidenceStrength"] = "INDIRECT"
        cov = coverage_service.calculate(chapter(), claims, evidence, [], [], {})
        self.assertEqual(cov["divisionCoverage"], 75.0)


class CoverageApiTests(AppCase, unittest.TestCase):
    def test_empty_chapter_and_import_blocked(self):
        cov = self.client.get("/api/coverage/CH02").get_json()
        self.assertEqual(cov["gate"], "NOT_STARTED")
        r = self.upload(CH01_HTML, "ch01.html").get_json()
        self.assertEqual(r["coverage"]["gate"], "BLOCKED")  # critical 01-F04 claim only has Rovo (INDIRECT) evidence
        self.assertTrue((self.tmp / "data" / "coverage" / "CH01.json").exists())
        self.assertEqual(self.client.get("/api/imports").get_json()[0]["gate"], "BLOCKED")
        self.assertEqual(len(self.client.get("/api/coverage").get_json()), 16)


if __name__ == "__main__":
    unittest.main()
