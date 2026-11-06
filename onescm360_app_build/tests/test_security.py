import os
import unittest
from unittest import mock

import app as app_module
from helpers import CH01_HTML, AppCase
from services.storage import safe_filename


class SecurityTests(AppCase, unittest.TestCase):
    def test_foreign_host_rejected(self):
        self.assertEqual(self.client.get("/api/meta", headers={"Host": "evil.example:8080"}).status_code, 403)
        self.assertEqual(self.client.get("/api/meta", headers={"Host": "127.0.0.1:8080"}).status_code, 200)

    def test_mutations_require_app_header(self):
        r = self.client.post("/api/rules", json={"category": "system", "source": "SAP"})
        self.assertEqual(r.status_code, 403)
        r = self.client.post("/api/import", data={"chapterId": "CH01"}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 403)

    def test_security_headers_and_pages(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"oneSCM360 Knowledge Studio", r.data)
        self.assertIn("frame-ancestors 'none'", r.headers["Content-Security-Policy"])
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(self.client.get("/static/app.js").status_code, 200)
        self.assertEqual(self.client.get("/api/imports").headers["Cache-Control"], "no-store")
        self.assertEqual(self.client.get("/api/unknown").status_code, 404)

    def test_no_tokens_in_meta(self):
        text = self.client.get("/api/meta").get_data(as_text=True).lower()
        for word in ("token", "secret", "password", "client_id"):
            self.assertNotIn(word, text)

    def test_only_loopback_allowed(self):
        with mock.patch.dict(os.environ, {"ONESCM_HOST": "0.0.0.0"}):
            with self.assertRaises(SystemExit):
                app_module.main()

    def test_safe_filename(self):
        self.assertEqual(safe_filename("..\\..\\Windows\\win.ini"), "win.ini")
        self.assertEqual(safe_filename("/etc/passwd"), "passwd")
        self.assertEqual(safe_filename("CON"), "datei")
        self.assertEqual(safe_filename("Kapitel 01 – Übersicht?.docx"), "Kapitel 01 _ Übersicht_.docx")

    def test_import_id_path_traversal(self):
        self.upload(CH01_HTML, "ch01.html")
        self.assertEqual(self.client.get("/api/imports/..%2F..%2Frules").status_code, 404)
        self.assertEqual(self.delete("/api/imports/IMP-..").status_code, 404)


if __name__ == "__main__":
    unittest.main()
