"""Period boundaries must preserve history and isolate every aggregate."""
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
import sqlite3
import tempfile
import unittest

from leanplan.domain import ValidationError
from leanplan.store import Store


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.day = date(2026, 11, 14)
        self.store = Store(Path(self.temp.name), lambda: self.day)
        self.store.save_settings({"sex": "male", "age": 22, "height": 173})
        self.macros = {"protein": 150, "fat": 60, "carbs": 200}
        self.yesterday = (self.day - timedelta(days=1)).isoformat()

    def tearDown(self):
        self.temp.cleanup()

    def seed(self):
        self.store.save_entry({"date": self.yesterday, "weight": 80,
                               "training_minutes": 40, **self.macros})
        self.store.save_entry({"date": self.day.isoformat(), **self.macros})

    def test_archive_keeps_today_and_carries_weight_without_a_fake_measurement(self):
        self.seed()
        before = self.store.state()
        archive_id = self.store.archive_period({"name": "Cut"})
        current = self.store.state()
        archived = self.store.archive(archive_id)
        self.assertEqual([r["date"] for r in current["entries"]], [self.day.isoformat()])
        self.assertEqual(current["entries"][0]["protein"], 150)
        self.assertIsNone(current["entries"][0]["weight"])
        self.assertEqual(current["summary"]["total_deficit"], before["today_stats"]["deficit"])
        self.assertEqual(current["summary"]["weight_count"], 0)
        self.assertEqual(current["summary"]["latest_weight"], 80)
        self.assertIsNone(current["summary"]["recent_average"])
        self.assertEqual(current["baseline"], {"weight": 80, "date": self.yesterday})
        self.assertEqual(current["journal_start"], self.day.isoformat())
        self.assertEqual(archived["entries"], before["entries"][:1])
        self.assertEqual(archived["end_date"], self.yesterday)
        self.assertTrue(archived["read_only"])
        self.assertEqual(len(current["archives"]), 1)
        self.assertNotIn("entries", current["archives"][0])

    def test_frozen_archive_ignores_later_profile_and_met_changes(self):
        self.seed()
        archive_id = self.store.archive_period({"name": "Cut"})
        frozen = self.store.archive(archive_id)
        self.store.save_settings({"age": 40, "height": 190, "sex": "female", "training_met": 6})
        self.store.save_entry({"date": self.day.isoformat(), "weight": 90})
        self.assertEqual(self.store.archive(archive_id), frozen)
        with self.assertRaises(ValidationError):
            self.store.save_entry({"date": self.yesterday, "weight": 75})
        with self.assertRaises(ValidationError):
            self.store.delete_entry(self.yesterday)
        self.assertEqual(self.store.archive(archive_id), frozen)

    def test_empty_or_today_only_cannot_create_empty_archives(self):
        for name in (None, "", " " * 4, "X" * 61, 42):
            with self.assertRaises(ValidationError):
                self.store.archive_period({"name": name})
        self.store.save_entry({"date": self.day.isoformat(), "weight": 80})
        with self.assertRaises(ValidationError):
            self.store.archive_period({"name": "Empty"})
        self.assertEqual(len(self.store.entries()), 1)
        self.assertEqual(self.store.state()["archives"], [])

    def test_multiple_periods_never_reuse_old_calories_or_weight_samples(self):
        self.seed()
        first = self.store.archive_period({"name": "Cut"})
        self.day += timedelta(days=1)
        second = self.store.archive_period({"name": "Maintain"})
        current = self.store.state()
        self.assertEqual(current["entries"], [])
        self.assertIsNone(current["summary"]["total_deficit"])
        self.assertIsNone(current["summary"]["average_calories"])
        self.assertEqual(current["summary"]["entry_count"], 0)
        self.assertEqual(current["summary"]["latest_weight"], 80)
        self.assertEqual(current["today_stats"]["bmr"], 1776.25)
        self.store.save_entry({"date": self.day.isoformat(), "weight": 81})
        self.assertEqual(self.store.state()["summary"]["weight_change"], 1)
        self.assertEqual(self.store.state()["summary"]["weight_count"], 1)
        self.assertEqual(len(self.store.archive(first)["entries"]), 1)
        self.assertEqual(len(self.store.archive(second)["entries"]), 1)

    def test_archive_and_reset_rollback_together_on_write_failure(self):
        self.seed()
        before = self.store.state()
        with self.store.connect() as db:
            db.execute("CREATE TRIGGER prevent_delete BEFORE DELETE ON entries BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.archive_period({"name": "Cut"})
        self.assertEqual(self.store.state(), before)

    def test_reopen_export_and_clear_preserve_full_backup(self):
        self.seed()
        archive_id = self.store.archive_period({"name": "Cut"})
        reopened = Store(Path(self.temp.name), lambda: self.day)
        self.assertEqual(reopened.archive(archive_id), self.store.archive(archive_id))
        exported = reopened.export()
        self.assertEqual(exported["version"], 4)
        self.assertEqual(len(exported["archives"]), 1)
        self.assertEqual(len(exported["entries"]), 1)
        reopened.clear_history()
        self.assertEqual(reopened.state()["archives"], [])
        self.assertIsNone(reopened.state()["baseline"])
        self.assertEqual(reopened.settings()["age"], 22)
        archive_counts = []
        for path in (Path(self.temp.name) / "backups").glob("*.sqlite3"):
            with closing(sqlite3.connect(path)) as db:
                archive_counts.append(db.execute("SELECT COUNT(*) FROM archives").fetchone()[0])
        self.assertIn(1, archive_counts)


if __name__ == "__main__":
    unittest.main()
