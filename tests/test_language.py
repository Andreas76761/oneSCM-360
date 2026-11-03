import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import app
import language_workflow


class LanguageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = app.Store(Path(self.temp.name) / "language.sqlite3")
        self.source = self.store.library.save({"id": app.uid(), "revision": 0, "title": "Vertrag öffnen",
            "block": dict(app.block(), text="Zuerst anmelden. Dann Vertrag öffnen.", note="PRIVATE_NOTE", status="Freigegeben")})

    def tearDown(self):
        self.temp.cleanup()

    def test_translation_requires_review_tracks_source_and_becomes_stale(self):
        target = {"id": app.uid(), "revision": 0, "title": "Open contract", "block": dict(app.block(), text="Sign in first. Then open the contract.", language="en", status="Freigegeben"),
                  "translation": {"source_id": self.source["id"], "source_revision": 1, "reviewed": False, "method": "Manuell"}}
        with self.assertRaises(app.Invalid):
            self.store.library.save(target)
        target["translation"]["reviewed"] = True
        translated = self.store.library.save(target)
        self.assertFalse(next(x for x in self.store.library.listing() if x["id"] == translated["id"])["translation_stale"])
        self.source["block"]["text"] = "Neuer Ablauf"
        self.store.library.save(self.source)
        self.assertTrue(next(x for x in self.store.library.listing() if x["id"] == translated["id"])["translation_stale"])
        outline = app.new_outline("English")
        outline["profile"]["language"] = "en"
        outline["chapters"][0]["blocks"] = [{**translated["block"], "library_ref": {"id": translated["id"], "revision": 1}}]
        saved = self.store.save(outline)
        manifest = app.compose(saved, saved["profile"])["manifest"]["texts"][0]
        self.assertEqual(manifest["translation"]["source_revision"], 1)
        self.assertEqual(manifest["library_ref"]["id"], translated["id"])

    def test_local_ai_returns_only_draft_and_sends_no_internal_note(self):
        response = MagicMock(status=200)
        response.read.return_value = json.dumps({"response": json.dumps({"title": "Open contract", "text": "Sign in. Open contract."})}).encode()
        connection = MagicMock()
        connection.getresponse.return_value = response
        with patch("language_workflow.http.client.HTTPConnection", return_value=connection) as factory:
            suggestion = language_workflow.generate(self.source, "translate", "en", "local-model")
        factory.assert_called_once_with("127.0.0.1", 11434, timeout=45)
        self.assertEqual(suggestion["status"], "Entwurf")
        self.assertNotIn("PRIVATE_NOTE", connection.request.call_args.args[2].decode())
        self.assertEqual(len(self.store.library.listing()), 1)  # No auto-save.
        response.read.return_value = b'{"response":"not json"}'
        with patch("language_workflow.http.client.HTTPConnection", return_value=connection), self.assertRaises(app.Invalid):
            language_workflow.generate(self.source, "shorten", "Kompakt", "local-model")


if __name__ == "__main__":
    unittest.main()
