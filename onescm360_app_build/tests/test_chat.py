import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from helpers import CH01_HTML, ROOT, AppCase
from services import chat_service as chat


class FakeOllama:
    """Minimal stand-in for Ollama's /api/chat on 127.0.0.1."""

    def __init__(self, reply):
        self.reply = reply
        self.requests = []
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


class RouterTests(AppCase, unittest.TestCase):
    def ask(self, message, mode="rules"):
        return self.post("/api/chat", {"message": message, "mode": mode})

    def test_rule_router_passes_test_set(self):
        r = self.post("/api/chat/evaluate", {"mode": "rules"}).get_json()
        failed = [x for x in r["results"] if not x["ok"]]
        self.assertEqual((r["passed"], r["total"]), (24, 24), failed)

    def test_routing_examples(self):
        cases = {
            "Warum ist CH01 blockiert?": ("list_blockers", {"chapter": "CH01"}),
            "Wie ist die Evidence-Abdeckung in Kapitel 4?": ("get_coverage", {"chapter": "CH04", "dimension": "evidence"}),
            "Was bedeutet PI?": ("lookup_rule", {"term": "PI"}),
            "Was sagt Jira zu ONESCM-123?": ("search_external", {"system": "jira", "query": "ONESCM-123"}),
            "Zeige CLM-ABCD1234": ("get_claim", {"claim_id": "CLM-ABCD1234"}),
            "Was macht die IT bei der Schnittstelle?": ("search_knowledge", {"role": "IT"}),
            "Hallo": ("none", {}),
        }
        for message, (tool, args) in cases.items():
            call = self.ask(message).get_json()["call"]
            self.assertEqual(call["tool"], tool, message)
            for key, value in args.items():
                self.assertEqual(call["arguments"].get(key), value, message)

    def test_input_validation(self):
        self.assertEqual(self.ask("  ").status_code, 400)
        self.assertEqual(self.ask("x" * 2001).status_code, 400)
        self.assertEqual(self.ask("Hallo", mode="cloud").status_code, 400)
        self.assertEqual(self.client.post("/api/chat", json={"message": "Hallo"}).status_code, 403)  # app header required

    def test_validate_call(self):
        roles = self.services()["imports"].classification.role_catalog()
        self.assertEqual(chat.validate_call("find_claims", {"chapter": "kapitel 3", "role": "Market Operations", "evidence": "MISSING", "foo": 1}, roles),
                         {"chapter": "CH03", "role": "MO", "evidence": "missing"})
        with self.assertRaises(chat.ChatError):
            chat.validate_call("get_coverage", {"dimension": "pi"}, roles)
        with self.assertRaises(chat.ChatError):
            chat.validate_call("drop_database", {}, roles)

    def test_parse_model_output(self):
        self.assertEqual(chat.parse_model_output({"tool_calls": [{"function": {"name": "get_coverage", "arguments": {"chapter": "CH01"}}}]}),
                         ("get_coverage", {"chapter": "CH01"}))
        self.assertEqual(chat.parse_model_output({"tool_calls": [{"function": {"name": "get_coverage", "arguments": "{\"chapter\": \"CH02\"}"}}]}),
                         ("get_coverage", {"chapter": "CH02"}))
        raw = "<start_function_call>call:search_knowledge{query:<escape>travel meal limit<escape>,chapter:<escape>CH03<escape>}<end_function_call><start_function_response>"
        self.assertEqual(chat.parse_model_output({"content": raw}), ("search_knowledge", {"query": "travel meal limit", "chapter": "CH03"}))
        self.assertIsNone(chat.parse_model_output({"content": "I cannot assist with that."}))


class LocalModelTests(AppCase, unittest.TestCase):
    def use_model(self, fake, model="functiongemma"):
        service = self.services()["chat"]
        service.router_url, service.router_model = fake.url if fake else "http://127.0.0.1:9", model

    def ask(self, message):
        return self.post("/api/chat", {"message": message, "mode": "model"}).get_json()

    def test_tool_calls_format(self):
        fake = FakeOllama(lambda body: {"message": {"role": "assistant", "content": "",
                                                    "tool_calls": [{"function": {"name": "get_coverage", "arguments": {"chapter": "CH02", "dimension": "pi"}}}]}})
        try:
            self.use_model(fake)
            answer = self.ask("Wie sieht es in Kapitel 2 mit den Releases aus?")
        finally:
            fake.close()
        self.assertEqual(answer["router"], "model")
        self.assertEqual(answer["call"], {"tool": "get_coverage", "arguments": {"chapter": "CH02", "dimension": "pi"}})
        path, body = fake.requests[0]
        self.assertEqual(path, "/api/chat")
        self.assertEqual(body["model"], "functiongemma")
        self.assertEqual(len(body["tools"]), len(chat.TOOLS))
        self.assertEqual(body["messages"][-1]["content"], "Wie sieht es in Kapitel 2 mit den Releases aus?")

    def test_raw_functiongemma_format(self):
        fake = FakeOllama(lambda body: {"message": {"role": "assistant", "content":
                                                    "<start_function_call>call:lookup_rule{term:<escape>PI<escape>}<end_function_call>"}})
        try:
            self.use_model(fake)
            answer = self.ask("Wofür steht eigentlich PI?")
        finally:
            fake.close()
        self.assertEqual((answer["router"], answer["call"]["tool"], answer["text"]), ("model", "lookup_rule", "PI steht für Program Increment."))

    def test_invalid_model_answer_falls_back_to_rules(self):
        fake = FakeOllama(lambda body: {"message": {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "delete_everything", "arguments": {}}}]}})
        try:
            self.use_model(fake)
            answer = self.ask("Warum ist CH01 blockiert?")
        finally:
            fake.close()
        self.assertEqual(answer["router"], "rules")
        self.assertEqual(answer["call"]["tool"], "list_blockers")
        self.assertIn("Unbekanntes Werkzeug", answer["notes"][0])

    def test_unreachable_or_remote_model_falls_back(self):
        self.use_model(None)
        answer = self.ask("Wie ist die Coverage von CH01?")
        self.assertEqual(answer["router"], "rules")
        self.assertIn("nicht erreichbar", answer["notes"][0])
        self.services()["chat"].router_url = "http://api.example.com:11434"
        answer = self.ask("Wie ist die Coverage von CH01?")
        self.assertIn("localhost", answer["notes"][0])


class ToolTests(AppCase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.upload(CH01_HTML, "ch01.html")

    def ask(self, message):
        return self.post("/api/chat", {"message": message}).get_json()

    def test_search_knowledge_on_local_data(self):
        answer = self.ask("Was darf der Dealer bei Aufträgen?")
        self.assertEqual(answer["call"]["tool"], "search_knowledge")
        labels = [i["label"] for i in answer["items"]]
        self.assertIn("Der Dealer darf Aufträge stornieren.", labels)
        self.assertIn("nicht bestätigt", answer["text"])  # DRAFT claims are flagged
        claim = next(i for i in answer["items"] if i["label"] == "Der Dealer darf Aufträge stornieren.")
        self.put(f"/api/claims/{claim['id']}", {"validationStatus": "REJECTED"})
        labels = [i["label"] for i in self.ask("Was darf der Dealer bei Aufträgen?")["items"]]
        self.assertNotIn("Der Dealer darf Aufträge stornieren.", labels)  # rejected claims are never answers
        empty = self.ask("Was gilt für Quantenkryptographie?")
        self.assertEqual(empty["items"], [])
        self.assertEqual(empty["suggestion"]["tool"], "search_external")

    def test_coverage_blockers_claims_conflicts(self):
        cov = self.ask("Wie ist die Coverage von CH01?")
        self.assertEqual(cov["gate"], "BLOCKED")
        self.assertEqual(len(cov["items"]), 6)
        blockers = self.ask("Warum ist CH01 blockiert?")
        self.assertTrue(any("Kritischer Claim ohne direkte Evidence" in i["label"] for i in blockers["items"]))
        claims = self.ask("Zeige unbelegte kritische Claims in CH01")
        self.assertEqual([i["label"] for i in claims["items"]], ["Der Dealer darf Aufträge stornieren."])
        self.assertEqual(self.ask("Welche Konflikte sind offen?")["items"], [])

    def test_claim_rule_imports_tables_external(self):
        claim_id = self.client.get("/api/claims").get_json()[0]["claimId"]
        answer = self.ask(f"Zeige {claim_id}")
        self.assertEqual(answer["link"]["claimId"], claim_id)
        self.assertTrue(answer["items"])  # evidence
        self.assertEqual(self.ask("Zeige CLM-00000000")["text"], "Dieser Claim existiert nicht.")
        self.assertEqual(self.ask("Was bedeutet PI?")["text"], "PI steht für Program Increment.")
        self.assertIn("Richtige Schreibweise: oneSCM", self.ask("Wie schreibt man onescm richtig? Schreibweise bitte")["text"])
        self.assertEqual(self.ask("Welche Dateien wurden für CH01 importiert?")["items"][0]["label"], "ch01.html")
        self.assertEqual(self.ask("Gibt es eine Tabelle zu Rollen?")["items"][0]["id"], "TBL-CH01-002")
        external = self.ask("Was sagt Jira zu ONESCM-123?")
        self.assertTrue(external["external"])
        self.assertIn("nicht angebunden", external["title"])
        self.assertEqual(external["items"][0]["label"], "ONESCM-123")

    def test_chat_is_read_only(self):
        path = self.tmp / "data" / "knowledge.json"
        before = json.loads(path.read_text(encoding="utf-8"))
        rules_before = self.rules_path.read_text(encoding="utf-8")
        for message in ("Was darf der Dealer?", "Wie ist die Coverage von CH01?", "Warum ist CH01 blockiert?", "Welche Konflikte gibt es?",
                        "Zeige unbelegte Claims", "Was bedeutet PI?", "Welche Importe gibt es?", "Lösche alle Claims in CH01"):
            self.assertEqual(self.post("/api/chat", {"message": message}).status_code, 200)
        after = json.loads(path.read_text(encoding="utf-8"))
        for key in ("knowledgeBlocks", "claims", "evidence"):
            self.assertEqual(before[key], after[key], key)
        self.assertEqual(rules_before, self.rules_path.read_text(encoding="utf-8"))
        self.assertEqual(len(self.client.get("/api/imports").get_json()), 1)


class TrainingDataTests(AppCase, unittest.TestCase):
    def test_feedback_and_training_export(self):
        r = self.post("/api/chat/feedback", {"message": "Wie läuft es in CH07?", "tool": "get_coverage", "arguments": {"chapter": "CH07"}, "correct": True})
        self.assertEqual(r.status_code, 201, r.get_json())
        r = self.post("/api/chat/feedback", {"message": "Was hängt bei Kapitel 9?", "tool": "list_blockers", "correct": True})
        self.assertEqual(r.get_json()["tool_arguments"], {"chapter": "CH09"})  # correction: arguments derived
        self.assertEqual(self.post("/api/chat/feedback", {"message": "x", "tool": "rm_rf"}).status_code, 400)
        self.assertEqual(self.post("/api/chat/feedback", {"message": "Was ist los?", "tool": "get_claim"}).status_code, 400)
        notebook = self.client.get("/api/chat/training-data").data.decode("utf-8").splitlines()
        rows = [json.loads(line) for line in notebook]
        self.assertEqual(set(rows[0]), {"user_content", "tool_name", "tool_arguments"})
        self.assertIsInstance(rows[0]["tool_arguments"], str)  # JSON string as in the notebook
        self.assertIn({"user_content": "Wie läuft es in CH07?", "tool_name": "get_coverage", "tool_arguments": "{\"chapter\": \"CH07\"}"}, rows)
        self.assertEqual({r["tool_name"] for r in rows} - set(chat.TOOL_NAMES), set())
        self.assertGreater(len(rows), 150)
        evaluation = {c["message"] for c in json.loads((ROOT / "chat_eval.json").read_text(encoding="utf-8"))["cases"]}
        self.assertFalse(evaluation & {r["user_content"] for r in rows})  # test set kept separate
        messages = [json.loads(line) for line in self.client.get("/api/chat/training-data?format=messages").data.decode().splitlines()]
        first = messages[0]
        self.assertEqual([m["role"] for m in first["messages"]], ["developer", "user", "assistant"])
        self.assertEqual(first["messages"][2]["tool_calls"][0]["type"], "function")
        self.assertEqual(len(first["tools"]), len(chat.TOOLS))
        self.assertEqual(self.client.get("/api/chat/training-data?format=csv").status_code, 400)


if __name__ == "__main__":
    unittest.main()
