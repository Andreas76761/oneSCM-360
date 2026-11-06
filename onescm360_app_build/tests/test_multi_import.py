import unittest

from helpers import CH01_HTML, AppCase, H, html_doc, make_docx, p
from services.classification_service import detect_language


class ClassificationTests(AppCase, unittest.TestCase):
    def classify(self, content, name):
        import io
        return self.client.post("/api/import/classify", data={"file": (io.BytesIO(content), name)}, headers=H,
                                content_type="multipart/form-data")

    def test_meta_lists_roles_and_domains(self):
        meta = self.client.get("/api/meta").get_json()
        self.assertEqual([r["id"] for r in meta["roles"]], ["Dealer", "MO", "HQ", "Market", "IT", "intern"])
        self.assertEqual(meta["roles"][1]["name"], "MO (Market Operations)")
        self.assertEqual([d["name"] for d in meta["domains"]],
                         ["Product Management", "Contract Generation", "Contract Management", "Customer Management",
                          "Finance Management", "Market Setting", "Admin Section"])

    def test_detect_from_file_name(self):
        r = self.classify(html_doc(p("Inhalt ohne weitere Hinweise.")), "CH05_Dealer_Finance-Management_DE.html")
        self.assertEqual(r.status_code, 200, r.get_json())
        d = r.get_json()
        self.assertEqual((d["chapterId"], d["chapterSource"]), ("CH05", "Dateiname"))
        self.assertEqual((d["language"], d["languageSource"]), ("DE", "Dateiname"))
        self.assertEqual((d["role"], d["roleSource"]), ("Dealer", "Dateiname"))
        self.assertEqual((d["domain"], d["domainSource"]), ("finance-management", "Dateiname"))
        self.assertEqual(self.classify(html_doc(p("x")), "Kapitel 12 - EN.htm").get_json()["chapterId"], "CH12")
        self.assertEqual(self.classify(html_doc(p("x")), "rovo_ch3_de_en.html").get_json()["language"], "DE+EN")

    def test_detect_from_content(self):
        doc = html_doc(p("05-F01 The invoice is created by Market Operations for the payment of the order."),
                       p("05-F02 Market Operations checks the invoice and the tax and the currency."),
                       p("05-F03 Market Operations can see all invoices in the finance overview."),
                       p("05-F04 The Dealer can view the payment status."))
        d = self.classify(doc, "antworten.html").get_json()
        self.assertEqual((d["chapterId"], d["chapterSource"]), ("CH05", "Inhalt"))
        self.assertEqual((d["language"], d["languageSource"]), ("EN", "Inhalt"))
        self.assertEqual((d["role"], d["roleSource"]), ("MO", "Inhalt"))
        self.assertEqual((d["domain"], d["domainSource"]), ("finance-management", "Inhalt"))

    def test_docx_and_undecided_values(self):
        docx = make_docx(["Der Dealer und Market Operations sehen den Vertrag.", "Die Ansicht ist für alle gleich."])
        d = self.classify(docx, "dokument.docx").get_json()
        self.assertEqual(d["chapterId"], "")  # no chapter hint at all
        self.assertEqual(d["role"], "")  # both roles equally present → "Alle Rollen"
        self.assertEqual(d["language"], "DE")

    def test_bilingual_content(self):
        language, source = detect_language("x.html", "Der Vertrag ist gültig und wird geprüft. The contract is valid and will be checked for the dealer.")
        self.assertEqual((language, source), ("DE+EN", "Inhalt"))

    def test_classify_rejects_bad_files_without_importing(self):
        self.assertEqual(self.classify(b"x", "notiz.txt").status_code, 415)
        self.assertEqual(self.classify(b"", "leer.html").status_code, 400)
        self.assertEqual(self.classify(b"PK\x03\x04kaputt", "kaputt.docx").status_code, 422)
        self.assertEqual(self.classify(html_doc(), "leer.html").status_code, 422)
        self.assertEqual(self.client.get("/api/imports").get_json(), [])
        self.assertEqual(list((self.tmp / "data" / "raw").iterdir()), [])


class RoleCatalogTests(AppCase, unittest.TestCase):
    def classify_name(self, name, body="Inhalt ohne Rollenhinweis."):
        import io
        r = self.client.post("/api/import/classify", data={"file": (io.BytesIO(html_doc(p(body))), name)}, headers=H,
                             content_type="multipart/form-data")
        return r.get_json()["role"]

    def test_role_from_file_name_and_aliases(self):
        self.assertEqual(self.classify_name("CH01_HQ_DE.html"), "HQ")
        self.assertEqual(self.classify_name("CH01_IT_DE.html"), "IT")
        self.assertEqual(self.classify_name("CH01_intern_DE.html"), "intern")
        self.assertEqual(self.classify_name("CH01_Market_DE.html"), "Market")
        self.assertEqual(self.classify_name("CH01_MO_DE.html"), "MO")
        self.assertEqual(self.classify_name("CH01_Market-Operation_DE.html"), "MO")  # longer alias wins over "Market"
        self.assertEqual(self.classify_name("CH01_Market-Setting_DE.html"), "")  # domain, not the role Market
        self.assertEqual(self.classify_name("CH01_Dealer_DE.html"), "Dealer")

    def test_short_aliases_are_case_sensitive(self):
        text = "It is what it is and it works for it. Mo and mo are not roles. It is fine."
        self.assertEqual(self.classify_name("a.html", text), "")
        self.assertEqual(self.classify_name("a.html", "The IT team runs the batch. IT monitors the interface. The dealer sees it."), "IT")

    def test_claims_use_role_ids(self):
        from services import claim_service as cs
        catalog = self.services()["imports"].classification.role_catalog()
        self.assertEqual(cs.analyse_statement("Market Operations genehmigt die Preise.", catalog, [])["role"], "MO")
        self.assertEqual(cs.analyse_statement("Das HQ gibt die Templates frei.", catalog, [])["role"], "HQ")
        self.assertEqual(cs.analyse_statement("Der Markt pflegt die Steuersätze.", catalog, [])["role"], "Market")
        self.assertEqual(cs.analyse_statement("Die IT überwacht die Schnittstelle.", catalog, [])["role"], "IT")
        self.assertEqual(cs.analyse_statement("Es wird intern geprüft und dann freigegeben.", catalog, [])["role"], "intern")
        self.assertEqual(cs.analyse_statement("It is checked later by the system.", catalog, [])["role"], "")
        a = cs.analyse_statement("Market Operations genehmigt Preisänderungen.", catalog, [])
        self.assertEqual(a["subject"], "MO")
        self.assertNotIn("market", a["object"])

    def test_import_normalises_role_alias(self):
        import io
        data = {"file": (io.BytesIO(CH01_HTML), "a.html"), "chapterId": "CH01", "language": "DE", "sourceType": "ROVO",
                "role": "Market Operations", "domain": ""}
        rec = self.client.post("/api/import", data=data, headers=H, content_type="multipart/form-data").get_json()["importRecord"]
        self.assertEqual(rec["role"], "MO")

    def test_coverage_roles_use_ids(self):
        chapter = self.client.get("/api/chapters/CH01").get_json()
        self.assertEqual(chapter["roles"], ["Dealer", "MO"])


class RoleDomainImportTests(AppCase, unittest.TestCase):
    def upload_scoped(self, content, name, role, domain, **kw):
        import io
        data = {"file": (io.BytesIO(content), name), "chapterId": kw.get("chapter", "CH01"), "language": "DE",
                "sourceType": "ROVO", "role": role, "domain": domain}
        return self.client.post("/api/import", data=data, headers=H, content_type="multipart/form-data")

    def test_import_stores_role_and_domain(self):
        doc = html_doc(p("F01 Aufträge werden im Portal angelegt."), p("F04 Market Operations genehmigt Preisänderungen."))
        r = self.upload_scoped(doc, "a.html", "Dealer", "contract-management")
        self.assertEqual(r.status_code, 201, r.get_json())
        rec = r.get_json()["importRecord"]
        self.assertEqual((rec["role"], rec["domain"], rec["domainName"]), ("Dealer", "contract-management", "Contract Management"))
        row = self.client.get("/api/imports").get_json()[0]
        self.assertEqual((row["role"], row["domain"]), ("Dealer", "contract-management"))
        claims = {c["canonicalStatement"]: c for c in self.client.get("/api/claims").get_json()}
        self.assertEqual(claims["Aufträge werden im Portal angelegt."]["role"], "Dealer")  # inherited from the file
        self.assertTrue(claims["Aufträge werden im Portal angelegt."]["roleFromImport"])
        self.assertEqual(claims["Market Operations genehmigt Preisänderungen."]["role"], "MO")  # explicit wins
        blocks = self.client.get("/api/knowledge-blocks").get_json()
        self.assertTrue(all(b["category"] == "Contract Management" and b["domain"] == "contract-management" for b in blocks))

    def test_invalid_role_or_domain(self):
        self.assertEqual(self.upload_scoped(CH01_HTML, "a.html", "Chef", "").status_code, 400)
        self.assertEqual(self.upload_scoped(CH01_HTML, "a.html", "", "unbekannt").status_code, 400)
        self.assertEqual(self.client.get("/api/imports").get_json(), [])

    def test_same_file_for_two_roles_is_two_imports(self):
        self.assertEqual(self.upload_scoped(CH01_HTML, "a.html", "Dealer", "").status_code, 201)
        self.assertEqual(self.upload_scoped(CH01_HTML, "a.html", "Dealer", "").status_code, 200)  # duplicate
        self.assertEqual(self.upload_scoped(CH01_HTML, "a.html", "MO", "").status_code, 201)
        self.assertEqual(len(self.client.get("/api/imports").get_json()), 2)

    def test_export_carries_role_and_domain(self):
        import json
        self.upload_scoped(CH01_HTML, "a.html", "Dealer", "market-setting")
        result = self.post("/api/sync/export", {"chapterId": "CH01"}).get_json()
        export = next(f for f in result["files"] if f.endswith("_export.json"))
        data = json.loads((self.onedrive / export).read_text(encoding="utf-8"))
        self.assertEqual((data["imports"][0]["role"], data["imports"][0]["domainName"]), ("Dealer", "Market Setting"))
        kb_csv = next(f for f in result["files"] if f.endswith("KnowledgeBlocks.csv"))
        self.assertIn(";Market Setting;", (self.onedrive / kb_csv).read_bytes().decode("utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
