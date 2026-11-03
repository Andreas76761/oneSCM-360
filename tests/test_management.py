import copy
import json
from pathlib import Path
import tempfile
import unittest

import app


class ManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = app.Store(Path(self.temp.name) / "management.sqlite3")

    def tearDown(self):
        self.temp.cleanup()

    def outline(self, titles):
        data = app.new_outline("Gliederung")
        data["chapters"] = [app.chapter(title, level) for title, level in titles]
        return self.store.save(data)

    def test_manual_version_and_history_are_independent(self):
        data = self.outline([("Einleitung", 1)])
        first_stamp = data["created_at"]
        data["metadata"].update(version="2026.11", owner="Redaktion", tags="Blueprint, Van", description="Manuell gepflegt")
        second = self.store.save(data)
        third = self.store.save(second)
        self.assertEqual(third["metadata"]["version"], "2026.11")
        self.assertEqual(third["revision"], 3)
        self.assertEqual(third["created_at"], first_stamp)
        self.assertEqual(self.store.snapshot(data["id"], 1)["metadata"]["version"], "1.0")
        self.assertEqual([r["revision"] for r in self.store.history(data["id"])], [3, 2, 1])
        self.assertEqual(self.store.snapshot(data["id"], 2)["metadata"]["owner"], "Redaktion")
        with self.assertRaises(app.Invalid):
            self.store.snapshot(data["id"], 99)

    def test_legacy_database_is_loaded_without_rewriting_history(self):
        legacy = app.new_outline("Bestehendes Handbuch")
        legacy.pop("metadata")
        legacy["revision"] = 1
        payload = json.dumps(legacy)
        with self.store.connect() as db:
            db.execute("INSERT INTO outlines VALUES(?,?,?)", (legacy["id"], 1, payload))
            db.execute("INSERT INTO history VALUES(?,?,?,?)", (legacy["id"], 1, "2025-01-01", payload))
        loaded = self.store.get(legacy["id"])
        self.assertEqual(loaded["metadata"]["version"], "1.0")
        self.assertEqual(loaded["chapters"][0]["lineage_id"], legacy["chapters"][0]["id"])
        loaded["metadata"]["version"] = "1.1"
        saved = self.store.save(loaded)
        self.assertEqual(len(saved["chapters"]), 3)
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT payload FROM history WHERE revision=1").fetchone()[0], payload)

    def test_missing_metadata_from_old_client_preserves_existing_values(self):
        data = self.outline([("Einleitung", 1)])
        data["metadata"]["version"] = "2.5"
        data = self.store.save(data)
        del data["metadata"]
        self.assertEqual(self.store.save(data)["metadata"]["version"], "2.5")

    def test_copy_retains_lineage_but_has_independent_ids(self):
        left = self.outline([("Verträge", 1), ("Übersicht", 2)])
        right = self.store.copy(left["id"])
        self.assertNotEqual(left["chapters"][0]["id"], right["chapters"][0]["id"])
        self.assertEqual(left["chapters"][0]["lineage_id"], right["chapters"][0]["lineage_id"])
        self.assertEqual(right["revision"], 1)
        self.assertEqual(app.compare_outlines(left, right)["counts"]["unchanged"], 2)

    def test_rename_move_add_remove_and_metadata_changes(self):
        left = self.outline([("Verträge", 1), ("Übersicht", 2), ("Alt", 1)])
        right = self.store.copy(left["id"])
        right["chapters"][0]["title"] = "Serviceverträge"
        right["chapters"][1]["level"] = 1
        right["chapters"][1]["goal"] = "Neues Ziel"
        right["chapters"].pop()
        right["chapters"].append(app.chapter("Neu"))
        right["metadata"]["version"] = "2.0"
        right = self.store.save(right)
        result = app.compare_outlines(left, right)
        self.assertEqual(result["counts"], {"added": 1, "removed": 1, "renamed": 1, "moved": 1, "changed": 1, "unchanged": 0})
        self.assertTrue(any(c["field"] == "metadata.version" for c in result["metadata_changes"]))
        self.assertEqual(result["right"][0]["match_basis"], "Kennung")
        self.assertEqual(result["right"][1]["changed_fields"], ["goal"])

    def test_insertion_does_not_mark_following_chapters_as_moved(self):
        left = self.outline([("A", 1), ("B", 1), ("C", 1)])
        right = copy.deepcopy(left)
        right["chapters"].insert(0, app.chapter("Neu"))
        result = app.compare_outlines(left, right)
        self.assertEqual(result["counts"]["added"], 1)
        self.assertEqual(result["counts"]["moved"], 0)
        self.assertEqual(result["counts"]["unchanged"], 3)

    def test_sibling_reordering_is_detected(self):
        left = self.outline([("A", 1), ("B", 1), ("C", 1)])
        right = copy.deepcopy(left)
        right["chapters"] = [right["chapters"][2], right["chapters"][0], right["chapters"][1]]
        self.assertEqual(app.compare_outlines(left, right)["counts"]["moved"], 1)

    def test_independent_import_matches_unique_paths_and_titles(self):
        left = self.outline([("Domäne A", 1), ("Suchen", 2), ("Domäne B", 1)])
        right = self.outline([("Domäne A", 1), ("Domäne B", 1), ("Suchen", 2)])
        result = app.compare_outlines(left, right)
        self.assertEqual(result["counts"]["moved"], 1)
        self.assertEqual(result["counts"]["added"], 0)
        self.assertEqual(result["right"][1]["children"][0]["match_basis"], "Eindeutiger Titel")

    def test_duplicate_titles_are_not_arbitrarily_matched(self):
        left = self.outline([("A", 1), ("Detail", 2), ("Detail", 2)])
        right = self.outline([("A", 1), ("Detail", 2), ("Detail", 2)])
        result = app.compare_outlines(left, right)
        self.assertEqual(result["counts"]["unchanged"], 1)
        self.assertEqual(result["counts"]["added"], 2)
        self.assertEqual(result["counts"]["removed"], 2)

    def test_empty_and_deep_trees(self):
        left = self.outline([])
        right = self.outline([(f"Ebene {i}", i) for i in range(1, 7)])
        result = app.compare_outlines(left, right)
        self.assertEqual(result["left"], [])
        self.assertEqual(result["counts"]["added"], 6)
        node = result["right"][0]
        for _ in range(5):
            node = node["children"][0]
        self.assertEqual(node["number"], "1.1.1.1.1.1")

    def test_invalid_metadata_and_duplicate_lineage_are_rejected(self):
        data = self.outline([("A", 1), ("B", 1)])
        data["metadata"]["version"] = "  "
        with self.assertRaises(app.Invalid):
            self.store.save(data)
        data["metadata"]["version"] = "2"
        data["chapters"][1]["lineage_id"] = data["chapters"][0]["lineage_id"]
        with self.assertRaises(app.Invalid):
            self.store.save(data)


if __name__ == "__main__":
    unittest.main()
