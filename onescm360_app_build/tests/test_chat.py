import json
import socket
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from helpers import CH01_HTML, ROOT, AppCase, H
from services import chat_service as chat
from services.policy_service import PolicyError, PolicyService

REGISTRY_TOOLS = ["search_knowledge", "search_manual", "search_jira", "search_confluence", "query_rovo",
                  "get_claims", "get_evidence", "calculate_coverage", "validate_chapter", "export_knowledge"]


class FakeOllama:
    """Minimal stand-in for Ollama's /api/chat on 127.0.0.1."""

    def __init__(self, reply):
        self.reply, self.requests = reply, []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append((self.path, body))
                data = json.dumps(outer.reply(body)).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class RegistryPolicyTests(AppCase, unittest.TestCase):
    def policy(self):
        return self.services()["policy"]

    def write(self, name, data):
        path = self.tmp / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_registry_v1(self):
        tools = self.policy().tools()
        self.assertEqual([t["name"] for t in tools], REGISTRY_TOOLS)
        for tool in tools:
            sec = tool["security"]
            self.assertFalse(sec["internet_access"], tool["name"])
            self.assertTrue(sec["audit"])
            self.assertIn(sec["network"], ("LOCAL_ONLY", "INTERNAL_ONLY"))
            self.assertIn("DELETE", sec["blocked_operations"])
        writers = [t["name"] for t in tools if t["security"]["writes"]]
        self.assertEqual(writers, ["export_knowledge"])
        self.assertTrue(self.policy().tool("export_knowledge")["security"]["confirmation_required"])
        chapter_enum = self.policy().tool("search_knowledge")["parameters"]["properties"]["chapter"]["enum"]
        self.assertEqual(chapter_enum, [f"CH{i:02d}" for i in range(1, 17)])
        for declaration in self.policy().declarations():
            self.assertEqual(set(declaration), {"name", "description", "parameters"})  # no security metadata for the model

    def test_policy_summary(self):
        summary = self.client.get("/api/chat/info").get_json()["policy"]
        self.assertEqual((summary["securityMode"], summary["defaultPolicy"]), ("INTERNAL_RESTRICTED", "DENY"))
        self.assertFalse(summary["externalNetwork"] or summary["externalLlm"] or summary["externalSearch"] or summary["telemetryExternal"])
        self.assertTrue(summary["networkGuard"])

    def test_unsafe_configuration_is_refused(self):
        registry = json.loads((ROOT / "tool_registry.json").read_text(encoding="utf-8"))
        registry["tools"][0]["security"]["internet_access"] = True
        with self.assertRaises(PolicyError):
            PolicyService(self.write("r.json", registry), ROOT / "security_policy.json", self.tmp / "a.jsonl")
        policy = json.loads((ROOT / "security_policy.json").read_text(encoding="utf-8"))
        with self.assertRaises(PolicyError):
            PolicyService(ROOT / "tool_registry.json", self.write("p1.json", {**policy, "default_policy": "ALLOW"}), self.tmp / "a.jsonl")
        with self.assertRaises(PolicyError):
            PolicyService(ROOT / "tool_registry.json", self.write("p2.json", {**policy, "external_llm": True}), self.tmp / "a.jsonl")

    def test_decisions(self):
        policy = json.loads((ROOT / "security_policy.json").read_text(encoding="utf-8"))
        policy["profiles"] = {"anna": {"tools": ["search_*", "get_claims", "export_knowledge"], "chapters": ["CH01"], "operations": ["READ"]}}
        service = PolicyService(ROOT / "tool_registry.json", self.write("p.json", policy), self.tmp / "a.jsonl", user="anna")
        self.assertTrue(service.decide("search_knowledge", {"query": "x", "chapter": "CH01"}).allowed)
        self.assertIn("nicht freigegeben", service.decide("search_knowledge", {"query": "x", "chapter": "CH02"}).reason)  # Gate 2
        self.assertIn("nicht berechtigt", service.decide("calculate_coverage", {"chapter": "CH01"}).reason)  # Gate 2
        self.assertIn("WRITE_LOCAL", service.decide("export_knowledge", {"chapter": "CH01"}).reason)  # operation
        self.assertIn("default DENY", service.decide("http_request", {"url": "https://x"}).reason)  # Gate 3
        self.assertIn("Pflichtparameter", service.decide("search_knowledge", {}).reason)
        unknown_user = PolicyService(ROOT / "tool_registry.json", self.write("p.json", policy), self.tmp / "a.jsonl", user="bob")
        self.assertFalse(unknown_user.decide("search_knowledge", {"query": "x"}).allowed)  # no profile → DENY
        policy["allowed_sources"] = ["onescm360"]
        service = PolicyService(ROOT / "tool_registry.json", self.write("p3.json", policy), self.tmp / "a.jsonl", user="anna")
        self.assertIn("jira_internal", service.decide("search_jira", {"query": "x"}).reason)

    def test_schema_validation_of_arguments(self):
        decision = self.policy().decide("calculate_coverage", {"chapter": "CH03", "dimensions": ["pi_status", "ROLES", "foo"], "extra": 1})
        self.assertEqual(decision.arguments, {"chapter": "CH03", "dimensions": ["PI_status", "roles"]})
        decision = self.policy().decide("search_knowledge", {"query": "x", "vehicle_type": "truck", "status": "released"})
        self.assertEqual(decision.arguments, {"query": "x", "status": "Released"})

    def test_audit_without_content(self):
        self.post("/api/chat", {"message": "Was gilt für geheime Rabattstaffeln beim Dealer?"})
        self.post("/api/chat", {"message": "Suche im Internet nach Rabattstaffeln"})
        entries = self.client.get("/api/chat/audit").get_json()
        self.assertTrue(entries)
        raw = (self.tmp / "data" / "audit.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("Rabattstaffeln", raw)  # neither the prompt nor the query text is logged
        denied = entries[0]
        self.assertEqual((denied["tool"], denied["result"], denied["executed"]), ("search_web", "DENIED", False))
        allowed = [e for e in entries if e["result"] == "ALLOWED"]
        self.assertTrue(all(e["arguments"].get("query", "").endswith("Zeichen>") for e in allowed if "query" in e["arguments"]))
        self.assertTrue(all(len(e["messageSha256"]) == 16 and e["user"] for e in entries))

    def test_network_guard_blocks_outbound(self):
        with self.assertRaises(PermissionError):
            socket.create_connection(("203.0.113.10", 80), timeout=1)
        fake = FakeOllama(lambda body: {"message": {}})
        try:
            with socket.create_connection(("127.0.0.1", fake.server.server_port), timeout=2):
                pass  # loopback stays allowed
        finally:
            fake.close()


class RouterTests(AppCase, unittest.TestCase):
    def ask(self, message, mode="rules"):
        return self.post("/api/chat", {"message": message, "mode": mode})

    def test_routing_test_suite(self):
        r = self.post("/api/chat/evaluate", {"mode": "rules"}).get_json()
        failed = [x for x in r["results"] if not x["ok"]]
        self.assertEqual((r["passed"], r["total"]), (30, 30), failed)

    def test_denied_requests_execute_nothing(self):
        for message, tool in (("Suche im Internet nach dem Wetter", "search_web"), ("Schick die Claims per E-Mail an a@b.de", "send_email"),
                              ("Lösche alle Claims in CH01", "delete_data")):
            answer = self.ask(message).get_json()
            self.assertTrue(answer["denied"], message)
            self.assertEqual(answer["steps"][0]["tool"], tool)
            self.assertEqual(answer["steps"][0]["policy"]["result"], "DENIED")
            self.assertEqual(answer["items"], [])

    def test_input_validation(self):
        self.assertEqual(self.ask("  ").status_code, 400)
        self.assertEqual(self.ask("x" * 2001).status_code, 400)
        self.assertEqual(self.ask("Hallo", mode="cloud").status_code, 400)
        self.assertEqual(self.client.post("/api/chat", json={"message": "Hallo"}).status_code, 403)
        self.assertEqual(self.ask("Hallo").get_json()["call"]["tool"], "none")

    def test_parse_model_output(self):
        self.assertEqual(chat.parse_model_output({"tool_calls": [{"function": {"name": "calculate_coverage", "arguments": "{\"chapter\": \"CH02\"}"}}]}),
                         ("calculate_coverage", {"chapter": "CH02"}))
        raw = "<start_function_call>call:search_knowledge{query:<escape>Service Contract Cancellation<escape>,vehicle_type:<escape>PC<escape>}<end_function_call>"
        self.assertEqual(chat.parse_model_output({"content": raw}),
                         ("search_knowledge", {"query": "Service Contract Cancellation", "vehicle_type": "PC"}))
        raw = "<start_function_call>call:calculate_coverage{chapter:<escape>CH03<escape>,dimensions:[<escape>PI_status<escape>]}<end_function_call>"
        self.assertEqual(chat.parse_model_output({"content": raw}), ("calculate_coverage", {"chapter": "CH03", "dimensions": ["PI_status"]}))
        self.assertIsNone(chat.parse_model_output({"content": "I cannot assist with that."}))


class LocalModelTests(AppCase, unittest.TestCase):
    def use(self, fake):
        self.services()["chat"].router_url = fake.url if fake else "http://127.0.0.1:9"

    def ask(self, message):
        return self.post("/api/chat", {"message": message, "mode": "model"}).get_json()

    def test_model_call_goes_through_policy(self):
        fake = FakeOllama(lambda body: {"message": {"tool_calls": [{"function": {"name": "calculate_coverage",
                                                                                 "arguments": {"chapter": "CH02", "dimensions": ["PI_status"]}}}]}})
        try:
            self.use(fake)
            answer = self.ask("Wie sieht es in Kapitel 2 mit den Releases aus?")
        finally:
            fake.close()
        self.assertEqual(answer["router"], "model")
        self.assertEqual(answer["call"], {"tool": "calculate_coverage", "arguments": {"chapter": "CH02", "dimensions": ["PI_status"]}})
        self.assertEqual(answer["steps"][0]["policy"]["result"], "ALLOWED")
        body = fake.requests[0][1]
        self.assertEqual([t["function"]["name"] for t in body["tools"]], REGISTRY_TOOLS)
        self.assertNotIn("security", json.dumps(body["tools"]))

    def test_model_cannot_call_unregistered_tools(self):
        fake = FakeOllama(lambda body: {"message": {"content": "<start_function_call>call:http_request{url:<escape>https://example.com<escape>}<end_function_call>"}})
        try:
            self.use(fake)
            answer = self.ask("Hol mir die Seite")
        finally:
            fake.close()
        self.assertTrue(answer["denied"])
        self.assertIn("default DENY", answer["text"])
        self.assertEqual(self.client.get("/api/chat/audit").get_json()[0]["result"], "DENIED")

    def test_unreachable_or_remote_model_falls_back(self):
        self.use(None)
        answer = self.ask("Berechne die Coverage für CH01")
        self.assertEqual((answer["router"], answer["call"]["tool"]), ("rules", "calculate_coverage"))
        self.assertIn("nicht erreichbar", answer["notes"][0])
        self.services()["chat"].router_url = "http://api.example.com:11434"
        self.assertIn("external_llm", self.ask("Berechne die Coverage für CH01")["notes"][0])


class ToolTests(AppCase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.upload(CH01_HTML, "ch01.html")

    def ask(self, message):
        return self.post("/api/chat", {"message": message}).get_json()

    def test_local_first_order(self):
        answer = self.ask("Was gilt für die Stornierung von Aufträgen beim Dealer?")
        self.assertEqual([(s["tool"], s["arguments"].get("status"), s["found"]) for s in answer["steps"]],
                         [("search_knowledge", "Released", False), ("search_knowledge", "Reviewed", False), ("search_knowledge", "Draft", True)])
        self.assertIn("nicht freigegeben", answer["text"])
        claim = next(i for i in answer["items"] if i["label"] == "Der Dealer darf Aufträge stornieren.")
        self.put(f"/api/claims/{claim['id']}", {"validationStatus": "CONFIRMED"})
        answer = self.ask("Was gilt für die Stornierung von Aufträgen beim Dealer?")
        self.assertEqual(len(answer["steps"]), 1)
        self.assertEqual(answer["items"][0]["status"], "Released")

    def test_no_source_and_never_internet(self):
        answer = self.ask("Was gilt für Quantenkryptographie im Fuhrpark?")
        self.assertEqual(answer["title"], chat.NO_SOURCE)
        self.assertEqual([s["tool"] for s in answer["steps"]], ["search_knowledge"] * 3 + ["search_manual", "search_jira", "search_confluence", "query_rovo"])
        self.assertNotIn("search_web", json.dumps(answer))

    def test_rule_set_is_released_knowledge(self):
        answer = self.ask("Wofür steht PI?")
        self.assertEqual(answer["items"][0]["label"], "PI = Program Increment")
        self.assertEqual(len(answer["steps"]), 1)

    def test_manual_jira_claims_evidence(self):
        manual = self.ask("Was steht im Handbuch zur Frage 01-F04?")
        self.assertEqual(manual["items"][0]["id"], "01-F04")
        self.assertIn("Der Dealer darf Aufträge stornieren.", manual["items"][0]["label"])
        jira = self.ask("Was steht in Jira zu ONESCM-123?")
        self.assertEqual(len(jira["items"]), 1)
        self.assertIn("nicht konfiguriert", jira["text"])
        claim_id = jira["items"][0]["claimId"]
        self.assertEqual(self.ask(f"Zeige {claim_id}")["items"][0]["id"], claim_id)
        evidence = self.ask(f"Hole die Evidence für {claim_id}")
        self.assertEqual({i["label"].split(" · ")[0] for i in evidence["items"]}, {"ROVO", "JIRA"})
        missing = self.ask("Zeige unbelegte kritische Claims in CH01")
        self.assertEqual([i["label"] for i in missing["items"]], ["Der Dealer darf Aufträge stornieren."])

    def test_coverage_and_validation(self):
        cov = self.ask("Prüfe Kapitel 01 auf PI-Relevanz")
        self.assertEqual([i["label"] for i in cov["items"]], ["PI-Status"])
        full = self.ask("Berechne die Coverage für CH01")
        self.assertEqual(len(full["items"]), 8)
        self.assertIn("CV (nicht in Readiness)", [i["label"] for i in full["items"]])
        validation = self.ask("Validiere Kapitel 1")
        self.assertEqual(validation["gate"], "BLOCKED")
        self.assertTrue(any("Kritischer Claim ohne direkte Evidence" in i["label"] for i in validation["items"]))
        self.assertIn("Kein Import", self.ask("Validiere Kapitel 2")["items"][0]["label"])
        self.upload(b"<p>Nur Text ohne Fragen.</p>", "kaputt.html", chapter="CH03")
        failed_only = self.ask("Validiere Kapitel 3")
        self.assertEqual(failed_only["gate"], "BLOCKED")  # no completed import at all
        self.assertTrue(any("fehlgeschlagen" in i["label"] and i["status"] == "WARNING" for i in failed_only["items"]))

    def test_export_requires_confirmation(self):
        answer = self.ask("Exportiere CH01 als CSV")
        self.assertTrue(answer["pendingConfirmation"])
        self.assertEqual(list(self.onedrive.rglob("*.csv")), [])  # nothing written yet
        self.assertEqual(self.post("/api/chat/execute", {"tool": "export_knowledge", "arguments": answer["call"]["arguments"]}).status_code, 400)
        done = self.post("/api/chat/execute", {"tool": "export_knowledge", "arguments": answer["call"]["arguments"], "confirm": True}).get_json()
        self.assertTrue(done["items"])
        self.assertTrue(list(self.onedrive.rglob("*_Claims.csv")))
        self.assertEqual(list(self.onedrive.rglob("*_export.json")), [])  # csv only
        self.assertEqual(list(self.onedrive.rglob("*.zip")), [])
        audit = self.client.get("/api/chat/audit").get_json()
        self.assertEqual((audit[0]["tool"], audit[0]["operation"], audit[0]["executed"]), ("export_knowledge", "WRITE_LOCAL", True))
        self.assertEqual(self.post("/api/chat/execute", {"tool": "delete_data", "arguments": {}, "confirm": True}).status_code, 403)

    def test_read_tools_do_not_change_data(self):
        path = self.tmp / "data" / "knowledge.json"
        before = json.loads(path.read_text(encoding="utf-8"))
        for message in ("Was darf der Dealer?", "Berechne die Coverage für CH01", "Validiere Kapitel 1", "Zeige unbelegte Claims",
                        "Wofür steht PI?", "Was steht in Jira zu ONESCM-123?", "Lösche alle Claims in CH01"):
            self.assertEqual(self.post("/api/chat", {"message": message}).status_code, 200)
        after = json.loads(path.read_text(encoding="utf-8"))
        for key in ("knowledgeBlocks", "claims", "evidence"):
            self.assertEqual(before[key], after[key], key)


class TrainingDataTests(AppCase, unittest.TestCase):
    def test_feedback_and_training_export(self):
        self.assertEqual(self.post("/api/chat/feedback", {"message": "Wie läuft es in CH07?", "tool": "calculate_coverage",
                                                          "arguments": {"chapter": "CH07"}}).status_code, 201)
        corrected = self.post("/api/chat/feedback", {"message": "Was hängt bei Kapitel 9?", "tool": "validate_chapter"}).get_json()
        self.assertEqual(corrected["tool_arguments"], {"chapter": "CH09"})
        self.assertEqual(self.post("/api/chat/feedback", {"message": "x", "tool": "search_web"}).status_code, 400)  # not in registry
        rows = [json.loads(line) for line in self.client.get("/api/chat/training-data").data.decode("utf-8").splitlines()]
        self.assertEqual(set(rows[0]), {"user_content", "tool_name", "tool_arguments"})
        self.assertIsInstance(rows[0]["tool_arguments"], str)
        self.assertIn({"user_content": "Wie läuft es in CH07?", "tool_name": "calculate_coverage", "tool_arguments": "{\"chapter\": \"CH07\"}"}, rows)
        self.assertEqual({r["tool_name"] for r in rows} - set(REGISTRY_TOOLS), set())
        evaluation = {c["message"] for c in json.loads((ROOT / "chat_eval.json").read_text(encoding="utf-8"))["cases"]}
        self.assertFalse(evaluation & {r["user_content"] for r in rows})
        messages = [json.loads(line) for line in self.client.get("/api/chat/training-data?format=messages").data.decode().splitlines()]
        self.assertEqual([m["role"] for m in messages[0]["messages"]], ["developer", "user", "assistant"])
        self.assertEqual([t["function"]["name"] for t in messages[0]["tools"]], REGISTRY_TOOLS)
        self.assertEqual(self.client.get("/api/chat/training-data?format=csv").status_code, 400)


if __name__ == "__main__":
    unittest.main()
