"""Mifflin-only calculations and compatibility with saved composition profiles."""
from datetime import date, timedelta
import json
from pathlib import Path
import tempfile
import unittest

from leanplan.domain import calculate_day, rounded, validate_entry, validate_settings
from leanplan.store import Store


TODAY = date(2026, 11, 14)
PROFILE = {"sex": "male", "age": 35, "height": 180}
LEGACY = {"fat_free_mass": 57, "body_composition_mode": "body_fat", "body_fat_percent": 10}


class MifflinTests(unittest.TestCase):
    def test_weekly_average_rounding_survives_binary_tie_noise(self):
        for sign in (1, -1):
            self.assertEqual(rounded(sign*12.772499999999994), sign*12.773)
            self.assertEqual(rounded(sign*12.772499999), sign*12.772)

    def calculate(self, patch=None, weight=80):
        # Include unfiltered old keys to catch accidental hidden formula switches.
        settings = {**validate_settings(PROFILE), **LEGACY, **(patch or {})}
        row = validate_entry({"date": TODAY.isoformat(), "protein": 150}, TODAY)
        return calculate_day(row, settings, weight)

    def test_legacy_composition_cannot_override_mifflin_or_total_weight(self):
        for patch in ({}, {"body_composition_mode": "fat_free_mass"},
                      {"fat_free_mass": 80}, {"body_fat_percent": 45}):
            with self.subTest(patch=patch):
                self.assertEqual(self.calculate(patch)["bmr"], 1755)
                self.assertEqual(self.calculate(patch, weight=90)["bmr"], 1855)
                self.assertEqual(self.calculate(patch)["bmr_formula"], "mifflin_st_jeor")

    def test_legacy_ffm_cannot_replace_missing_profile_data(self):
        for missing in ("age", "height", "sex"):
            with self.subTest(missing=missing):
                result = self.calculate({missing: None})
                self.assertIsNone(result["bmr"])
                self.assertIsNone(result["deficit"])
                self.assertEqual(result["calories"], 600)
        self.assertIsNone(self.calculate(weight=None)["bmr"])

    def test_settings_discard_obsolete_keys_without_rejecting_old_values(self):
        settings = validate_settings({"height": 181, **LEGACY}, {**PROFILE, **LEGACY})
        self.assertEqual(settings["height"], 181)
        self.assertEqual(settings["age"], 35)
        self.assertTrue(set(LEGACY).isdisjoint(settings))
        settings = validate_settings({"body_fat_percent": 100, "fat_free_mass": 1000}, settings)
        self.assertTrue(set(LEGACY).isdisjoint(settings))

    def test_reopening_old_profile_preserves_records_and_does_not_mutate_storage(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder), lambda: TODAY)
            store.save_settings(PROFILE)
            store.save_entry({"date": TODAY.isoformat(), "weight": 80,
                              "protein": 150, "calorie_override": 1020})
            with store.connect() as db:
                raw_settings = json.dumps({**store.settings(db), **LEGACY})
                db.execute("UPDATE settings SET value=? WHERE id=1", (raw_settings,))
            original_entries = store.entries()
            reopened = Store(Path(folder), lambda: TODAY)
            state = reopened.state()
            self.assertEqual(state["today_stats"]["bmr"], 1755)
            self.assertEqual(state["today_stats"]["calories"], 1020)
            self.assertEqual(state["today_stats"]["calories_source"], "manual")
            self.assertTrue(set(LEGACY).isdisjoint(state["settings"]))
            self.assertEqual(reopened.entries(), original_entries)
            with reopened.connect() as db:
                self.assertEqual(db.execute("SELECT value FROM settings WHERE id=1").fetchone()[0], raw_settings)
            reopened.save_settings({"height": 181})
            self.assertEqual(reopened.state()["today_stats"]["bmr"], 1761.25)
            self.assertEqual(reopened.entries(), original_entries)

    def test_legacy_cunningham_archive_is_frozen_and_new_period_uses_mifflin(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder), lambda: TODAY)
            store.save_settings(PROFILE)
            yesterday = (TODAY-timedelta(days=1)).isoformat()
            store.save_entry({"date": yesterday, "weight": 80, "protein": 150})
            store.save_entry({"date": TODAY.isoformat(), "protein": 150})
            archive_id = store.archive_period({"name": "Previous cut"})
            # Represent an already saved archive from the composition release.
            frozen = store.archive(archive_id)
            frozen["settings"].update(LEGACY)
            for row in (*frozen["entries"], frozen["today_stats"]):
                row.update(bmr=1925.2, bmr_formula="cunningham_1991", effective_fat_free_mass=72,
                           tdee=2075.2, deficit=1475.2)
            frozen["summary"]["total_deficit"] = 1475.2
            raw = json.dumps(frozen)
            with store.connect() as db:
                db.execute("UPDATE archives SET snapshot=?,summary=? WHERE id=?",
                           (raw, json.dumps(frozen["summary"]), archive_id))
            reopened = Store(Path(folder), lambda: TODAY)
            self.assertEqual(reopened.state()["today_stats"]["bmr"], 1755)
            self.assertEqual(reopened.state()["summary"]["weight_count"], 0)
            reopened.save_settings({"age": 36})
            self.assertEqual(reopened.state()["today_stats"]["bmr"], 1750)
            self.assertEqual(reopened.archive(archive_id), frozen)
            with reopened.connect() as db:
                self.assertEqual(db.execute("SELECT snapshot FROM archives WHERE id=?", (archive_id,)).fetchone()[0], raw)
            self.assertEqual(reopened.export()["archives"][0], frozen)

    def test_new_archive_records_mifflin_and_keeps_today_and_carried_weight(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder), lambda: TODAY)
            store.save_settings(PROFILE)
            store.save_entry({"date": (TODAY-timedelta(days=1)).isoformat(), "weight": 80, "protein": 150})
            store.save_entry({"date": TODAY.isoformat(), "protein": 100, "calorie_override": 500})
            archive_id = store.archive_period({"name": "Cut"})
            archive = store.archive(archive_id)
            self.assertEqual(archive["entries"][0]["bmr"], 1755)
            self.assertEqual(archive["entries"][0]["bmr_formula"], "mifflin_st_jeor")
            current = store.state()
            self.assertEqual(current["today_stats"]["bmr"], 1755)
            self.assertEqual(current["today_stats"]["calories"], 500)
            self.assertEqual(current["summary"]["weight_count"], 0)
            self.assertEqual(current["summary"]["total_deficit"], 1355)


if __name__ == "__main__":
    unittest.main()
