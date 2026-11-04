"""Synthetic Jira export fixtures; no uploaded tickets or real personal data."""
import json
from pathlib import Path
import tempfile
import unittest

import app
import jira_import
import sources


def table_export(count=2):
    headers = '<tr><th data-id="issuekey">Key</th><th data-id="summary">Summary</th><th data-id="description">Beschreibung</th><th data-id="assignee">Bearbeiter</th><th data-id="reporter">Erfasser</th><th data-id="status">Status</th></tr>'
    rows = []
    for i in range(1, count + 1):
        rows.append(f'''<tr class="issuerow"><td class="issuekey"><a href="https://invalid.example/browse/SYN-{i}">SYN-{i}</a></td>
          <td class="summary">Synthetischer Vertrag {i}</td>
          <td class="description"><h3>Voraussetzung {i}</h3><p>Beleg {i} erhalten.</p><ul><li>Vertrag öffnen</li><li>Prüfen</li></ul></td>
          <td class="assignee">Fiktive Testperson</td><td class="reporter">Erfundene Meldeperson</td><td class="status">In Prüfung</td></tr>''')
    return ('<!doctype html><html><head><meta charset="utf-8"></head><body><table>' + headers + ''.join(rows) + '</table></body></html>').encode()


class JiraImportReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "jira.sqlite3"
        self.store = app.Store(self.path)

    def count(self, table):
        with self.store.connect() as db:
            return db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]

    def test_table_export_keeps_one_structured_chunk_per_ticket(self):
        result = self.store.sources.upload("synthetic.html", table_export(3), {"kind": "Jira"})
        chunks = self.store.sources.chunks(result["id"])
        self.assertEqual(len(chunks), 3)
        for i, chunk in enumerate(chunks, 1):
            self.assertEqual(chunk["location"], f"SYN-{i}")
            self.assertEqual(chunk["details"]["ticket_key"], f"SYN-{i}")
            self.assertEqual(chunk["details"]["jira_fields"]["status"], "In Prüfung")
            self.assertEqual(chunk["details"]["text_format"], "markdown")
            self.assertIn(f"# SYN-{i} · Synthetischer Vertrag {i}", chunk["text"])
            self.assertIn(f"### Voraussetzung {i}", chunk["text"])
            self.assertIn("- Vertrag öffnen", chunk["text"])
            for other in range(1, 4):
                if other != i:
                    self.assertNotIn(f"SYN-{other}", chunk["text"])

    def test_word_html_headings_preserve_ticket_boundaries_and_content(self):
        raw = b'''<html><body><h1>SYN-10 First</h1><p>FIRST_TICKET_TEXT</p>
          <h2>Details</h2><p>FIRST_DETAIL_TEXT</p><h1>SYN-11 Second</h1>
          <p>SECOND_TICKET_TEXT</p><h3>Result</h3><p>SECOND_RESULT_TEXT</p></body></html>'''
        result = self.store.sources.upload("synthetic.doc", raw, {"kind": "Jira"})
        chunks = self.store.sources.chunks(result["id"])
        self.assertEqual([c["location"] for c in chunks], ["SYN-10", "SYN-11"])
        self.assertIn("## Details", chunks[0]["text"])
        self.assertIn("FIRST_DETAIL_TEXT", chunks[0]["text"])
        self.assertNotIn("SECOND_", chunks[0]["text"])
        self.assertNotIn("FIRST_", chunks[1]["text"])
        self.assertIn("### Result", chunks[1]["text"])
        self.assertIn("SECOND_RESULT_TEXT", chunks[1]["text"])

    def test_person_fields_comments_metadata_and_staging_are_scrubbed(self):
        raw = '''<html><body><h1>SYN-25 Testperson Alpha Vertragsprüfung</h1>
          <table><tr><td>Assignee:</td><td>Testperson Alpha</td></tr>
          <tr><td>Reporter:</td><td>Testperson Beta</td></tr></table>
          <div class="comment-header">Comment by Testperson Gamma [2026-11-04]</div>
          <p>Testperson Alpha und Testperson Beta prüfen mit Testperson Gamma den Vertrag.</p>
          <a class="user-hover" data-username="synthetic_account_4" href="/secure/ViewProfile.jspa?name=synthetic_account_4">Testperson Delta</a>
          <p>Testperson Delta synthetic_account_4 fake.account@example.invalid USERID: synthetic_id_42 FIN: synthetic_vin_43</p>
          <script>PRIVATE_SCRIPT_SENTINEL</script><div hidden>PRIVATE_HIDDEN_SENTINEL</div>
          <img src="data:image/png;base64,PRIVATE_IMAGE_SENTINEL"><!--PRIVATE_COMMENT_SENTINEL-->
          <p>BUSINESS_CONTENT_SURVIVES</p></body></html>'''.encode()
        job = self.store.sources.imports.start("Testperson Alpha.html", raw,
            {"kind": "Jira", "origin": "Testperson Beta", "release": "Testperson Gamma"})
        with self.store.connect() as db:
            staged = '\n'.join(str(row) for table in ['source_import_jobs', 'source_import_parts']
                               for row in db.execute("SELECT * FROM " + table))
        forbidden = ["Testperson Alpha", "Testperson Beta", "Testperson Gamma", "Testperson Delta",
                     "synthetic_account_4", "fake.account@example.invalid", "synthetic_id_42", "synthetic_vin_43",
                     "PRIVATE_SCRIPT_SENTINEL", "PRIVATE_HIDDEN_SENTINEL", "PRIVATE_IMAGE_SENTINEL", "PRIVATE_COMMENT_SENTINEL"]
        for value in forbidden:
            self.assertNotIn(value, staged)
        job = self.store.sources.imports.step(job)
        with self.store.connect() as db:
            raw_saved = db.execute("SELECT raw FROM sources WHERE id=?", (job["result"]["id"],)).fetchone()[0].decode()
        chunks = json.dumps(self.store.sources.chunks(job["result"]["id"]), ensure_ascii=False)
        for value in forbidden:
            self.assertNotIn(value, raw_saved + chunks + json.dumps(job))
        self.assertIn("BUSINESS_CONTENT_SURVIVES", raw_saved)
        self.assertNotIn("<script", raw_saved)
        self.assertNotIn("href=", raw_saved)

    def test_51_ticket_import_processes_25_per_step_and_resumes_after_restart(self):
        job = self.store.sources.imports.start("synthetic.html", table_export(51), {"kind": "Jira"})
        self.assertEqual((job["processed"], job["total"]), (0, 51))
        old = dict(job)
        job = self.store.sources.imports.step(job)
        self.assertEqual(job["processed"], 25)
        self.assertEqual(self.count("sources"), 0)
        self.assertEqual(self.count("chunks"), 0)
        with self.assertRaises(app.Conflict):
            self.store.sources.imports.step(old)
        self.store = app.Store(self.path)
        resumed = self.store.sources.imports.listing()[0]
        self.assertEqual(resumed, job)
        job = self.store.sources.imports.step(resumed)
        self.assertEqual(job["processed"], 50)
        self.assertEqual(self.count("sources"), 0)
        job = self.store.sources.imports.step(job)
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["processed"], 51)
        self.assertEqual(self.count("chunks"), 51)
        self.assertEqual(self.count("source_import_parts"), 0)
        self.assertEqual(self.store.sources.imports.listing(), [])
        self.assertEqual(self.store.sources.imports.step(job), job)
        self.assertEqual(self.count("sources"), 1)

    def test_cancel_discards_partial_work_without_publishing_or_resurrecting_it(self):
        job = self.store.sources.imports.start("synthetic.html", table_export(26), {"kind": "Jira"})
        job = self.store.sources.imports.step(job)
        stale = dict(job)
        cancelled = self.store.sources.imports.cancel(job)
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(self.count("source_import_parts"), 0)
        self.assertEqual(self.count("sources"), 0)
        self.assertEqual(self.count("chunks"), 0)
        self.assertEqual(self.store.sources.imports.step(stale), cancelled)
        self.store = app.Store(self.path)
        self.assertEqual(self.store.sources.imports.listing(), [])
        self.assertEqual(self.store.sources.imports.cancel(cancelled), cancelled)

    def test_duplicate_ticket_key_aborts_without_partial_storage(self):
        raw = table_export(2).replace(b'SYN-2', b'SYN-1')
        with self.assertRaises(ValueError):
            self.store.sources.imports.start("duplicate.html", raw, {"kind": "Jira"})
        for table in ["sources", "chunks", "source_import_jobs", "source_import_parts"]:
            self.assertEqual(self.count(table), 0)

    def test_already_imported_scrubbed_export_is_deduplicated(self):
        raw = table_export(2)
        source = self.store.sources.upload("first.html", raw, {"kind": "Jira"})
        result = self.store.sources.imports.start("again.html", raw, {"kind": "Jira"})
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["result"]["id"], source["id"])
        self.assertTrue(result["result"]["duplicate"])
        self.assertEqual(self.count("source_import_jobs"), 0)

    def test_empty_and_over_20_mib_fail_before_any_staging(self):
        self.assertEqual(sources.MAX_FILE, 20 * 1024 * 1024)
        for raw in [b'', b' ' * (sources.MAX_FILE + 1)]:
            with self.subTest(size=len(raw)):
                with self.assertRaises(ValueError):
                    self.store.sources.imports.start("limit.html", raw, {"kind": "Jira"})
                with self.assertRaises(ValueError):
                    self.store.sources.upload("limit.html", raw, {"kind": "Jira"})
        self.assertEqual(self.count("source_import_jobs"), 0)
        self.assertEqual(self.count("sources"), 0)

    def test_parser_resource_limit_never_silently_loses_later_ticket(self):
        raw = (b'<html><body><h1>SYN-91 Large</h1><p>' + b'x' * (11 * 1024 * 1024)
               + b' FIRST_END_SENTINEL</p><h1>SYN-92 Last</h1><p>LAST_TICKET_SENTINEL</p></body></html>')
        self.assertLess(len(raw), sources.MAX_FILE)
        try:
            job = self.store.sources.imports.start("large.html", raw, {"kind": "Jira"})
        except ValueError:
            self.assertEqual(self.count("source_import_jobs"), 0)
            self.assertEqual(self.count("sources"), 0)
            return
        job = self.store.sources.imports.step(job)
        chunks = self.store.sources.chunks(job["result"]["id"])
        self.assertEqual([c["location"] for c in chunks], ["SYN-91", "SYN-92"])
        self.assertIn("FIRST_END_SENTINEL", chunks[0]["text"])
        self.assertIn("LAST_TICKET_SENTINEL", chunks[1]["text"])

    def test_excessive_nesting_aborts_without_partial_import(self):
        raw = (b'<html><body><h1>SYN-71 Deep</h1>' + b'<div>' * 300
               + b'DEEP_CONTENT' + b'</div>' * 300 + b'<h1>SYN-72 Last</h1></body></html>')
        with self.assertRaises(ValueError):
            self.store.sources.imports.start("deep.html", raw, {"kind": "Jira"})
        self.assertEqual(self.count("source_import_jobs"), 0)
        self.assertEqual(self.count("sources"), 0)
