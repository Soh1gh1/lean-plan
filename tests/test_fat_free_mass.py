"""FFM formula selection, independent arithmetic and existing-data compatibility."""
from datetime import date, timedelta
import json
from pathlib import Path
import tempfile
import unittest

from leanplan.domain import ValidationError, build_state, calculate_day, validate_entry, validate_settings
from leanplan.store import Store


TODAY = date(2026, 11, 14)
PROFILE = {"age": 35, "height": 180, "sex": "male"}


class FatFreeMassTests(unittest.TestCase):
    def calculate(self, profile=None, weight=80):
        row = validate_entry({"date": TODAY.isoformat(), "protein": 150, "carbs": 200,
                              "fat": 60, "training_minutes": 45, "training_met": 4,
                              "steps_kcal": 250}, TODAY)
        return calculate_day(row, validate_settings(profile or {}), weight)

    def test_independent_ffm_example_and_balance(self):
        # 370 + 21.6*57 = 1601.2. Training still uses 80 kg: 189 kcal.
        result = self.calculate({**PROFILE, "fat_free_mass": 57})
        self.assertEqual(result["bmr"], 1601.2)
        self.assertEqual(result["bmr_formula"], "cunningham_1991")
        self.assertEqual(result["training_kcal"], 189)
        self.assertEqual(result["tdee"], 2261)
        self.assertEqual(result["deficit"], 321)

    def test_ffm_only_needs_ffm_and_does_not_invent_a_weight(self):
        result = self.calculate({"fat_free_mass": 57}, weight=None)
        self.assertEqual(result["bmr"], 1601.2)
        self.assertIsNone(result["effective_weight"])
        self.assertIsNone(result["training_kcal"])
        self.assertEqual(result["tdee"], 2072)

    def test_ffm_formula_does_not_use_other_profile_inputs(self):
        for profile in ({}, PROFILE, {"age": 75, "height": 150, "sex": "female"}):
            self.assertEqual(self.calculate({**profile, "fat_free_mass": 57})["bmr"], 1601.2)
        self.assertEqual(self.calculate({"fat_free_mass": 58})["bmr"], 1622.8)
        self.assertEqual(self.calculate({"fat_free_mass": 57}, weight=90)["bmr"], 1601.2)
        self.assertEqual(self.calculate({"fat_free_mass": 57}, weight=90)["training_kcal"], 212.625)

    def test_empty_ffm_restores_mifflin_and_its_required_inputs(self):
        for value in (None, ""):
            result = self.calculate({**PROFILE, "fat_free_mass": value})
            self.assertEqual(result["bmr"], 1755)
            self.assertEqual(result["bmr_formula"], "mifflin_st_jeor")
            self.assertIsNone(self.calculate({"fat_free_mass": value})["bmr"])

    def test_ffm_validation_does_not_treat_zero_as_missing(self):
        self.assertEqual(validate_settings({"fat_free_mass": "57,5"})["fat_free_mass"], 57.5)
        for value in (0, -1, 500.1, True, "nan", "inf", "text"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_settings({"fat_free_mass": value})

    def test_inconsistent_weight_cannot_produce_an_ffm_bmr_or_silent_fallback(self):
        result = self.calculate({**PROFILE, "fat_free_mass": 81}, weight=80)
        self.assertIsNone(result["bmr"])
        self.assertIsNone(result["tdee"])
        self.assertEqual(result["bmr_formula"], "cunningham_1991")
        self.assertEqual(self.calculate({"fat_free_mass": 80})["bmr"], 2098)

    def test_old_settings_roundtrip_and_clear_without_changing_records(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory), lambda: TODAY)
            with store.connect() as db:
                db.execute("UPDATE settings SET value=?", (json.dumps(PROFILE),))
            self.assertIsNone(store.settings()["fat_free_mass"])
            self.assertEqual(store.settings()["body_composition_mode"], "fat_free_mass")
            self.assertIsNone(store.settings()["body_fat_percent"])
            store.save_entry({"date": TODAY.isoformat(), "weight": 80})
            before = store.entries()
            store.save_settings({"fat_free_mass": 57})
            reopened = Store(Path(directory), lambda: TODAY)
            self.assertEqual(reopened.state()["today_stats"]["bmr"], 1601.2)
            self.assertEqual(reopened.export()["settings"]["fat_free_mass"], 57)
            self.assertEqual(reopened.entries(), before)
            reopened.save_settings({"fat_free_mass": None})
            self.assertEqual(reopened.state()["today_stats"]["bmr"], 1755)
            self.assertEqual(reopened.entries(), before)

    def test_ffm_greater_than_latest_weight_is_rejected_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory), lambda: TODAY)
            store.save_entry({"date": TODAY.isoformat(), "weight": 80})
            with self.assertRaises(ValidationError):
                store.save_settings({"fat_free_mass": 81, "age": 35})
            self.assertIsNone(store.settings()["fat_free_mass"])
            self.assertIsNone(store.settings()["age"])
            with self.assertRaises(ValidationError):
                store.onboard({"settings": {"fat_free_mass": 81}, "weight": 80})
            self.assertFalse(store.settings()["onboarding_done"])

    def test_archives_keep_their_formula_and_ffm_after_profile_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory), lambda: TODAY)
            store.save_settings({**PROFILE, "fat_free_mass": 57})
            store.save_entry({"date": (TODAY-timedelta(days=1)).isoformat(),
                              "weight": 80, "protein": 150})
            archive_id = store.archive_period({"name": "Cut"})
            frozen = store.archive(archive_id)
            self.assertEqual(frozen["settings"]["fat_free_mass"], 57)
            self.assertEqual(frozen["entries"][0]["bmr"], 1601.2)
            with self.assertRaises(ValidationError):
                store.save_settings({"fat_free_mass": 81})
            store.save_settings({"fat_free_mass": None})
            self.assertEqual(store.state()["today_stats"]["bmr"], 1755)
            self.assertEqual(store.archive(archive_id), frozen)

    def test_percentage_mode_tracks_weight_and_ignores_inactive_ffm(self):
        profile = {**PROFILE, "body_composition_mode": "body_fat",
                   "body_fat_percent": 10, "fat_free_mass": 57}
        for weight, ffm, bmr in ((80, 72, 1925.2), (90, 81, 2119.6)):
            with self.subTest(weight=weight):
                result = self.calculate(profile, weight=weight)
                self.assertEqual(result["effective_fat_free_mass"], ffm)
                self.assertEqual(result["bmr"], bmr)
                self.assertEqual(result["bmr_formula"], "cunningham_1991")
        fixed = self.calculate({**profile, "body_composition_mode": "fat_free_mass"}, weight=90)
        self.assertEqual(fixed["effective_fat_free_mass"], 57)
        self.assertEqual(fixed["bmr"], 1601.2)

    def test_percentage_mode_requires_weight_and_only_empty_active_input_falls_back(self):
        profile = {**PROFILE, "body_composition_mode": "body_fat", "body_fat_percent": 10,
                   "fat_free_mass": 57}
        missing = self.calculate(profile, weight=None)
        self.assertIsNone(missing["bmr"])
        self.assertIsNone(missing["effective_fat_free_mass"])
        self.assertEqual(missing["bmr_formula"], "cunningham_1991")
        for value in (None, ""):
            empty = self.calculate({**profile, "body_fat_percent": value})
            self.assertEqual(empty["bmr"], 1755)
            self.assertEqual(empty["bmr_formula"], "mifflin_st_jeor")
        zero = self.calculate({**profile, "body_fat_percent": 0})
        self.assertEqual(zero["effective_fat_free_mass"], 80)
        self.assertEqual(zero["bmr"], 2098)

    def test_percentage_uses_each_dates_own_weight_with_no_fabricated_measurements(self):
        settings = validate_settings({"body_composition_mode": "body_fat", "body_fat_percent": 10})
        rows = [validate_entry({"date": "2026-11-01", "weight": 80}, TODAY),
                validate_entry({"date": "2026-11-02", "protein": 150}, TODAY),
                validate_entry({"date": TODAY.isoformat(), "weight": 90}, TODAY)]
        state = build_state(rows, settings, TODAY)
        self.assertEqual([row["bmr"] for row in state["entries"]], [1925.2, 1925.2, 2119.6])
        self.assertIsNone(state["entries"][1]["weight"])
        self.assertEqual(state["summary"]["weight_count"], 2)

    def test_percentage_and_mode_validation(self):
        self.assertEqual(validate_settings({"body_fat_percent": "10,5"})["body_fat_percent"], 10.5)
        for value in (-1, 100, 101, True, "nan", "inf", "text"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_settings({"body_fat_percent": value})
        for value in (None, "percent", "", True):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_settings({"body_composition_mode": value})

    def test_mode_roundtrip_preserves_values_and_percentage_archives(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory), lambda: TODAY)
            store.save_settings({**PROFILE, "fat_free_mass": 57})
            store.save_entry({"date": (TODAY-timedelta(days=1)).isoformat(), "weight": 80})
            store.save_settings({"body_composition_mode": "body_fat", "body_fat_percent": 10})
            store.save_entry({"date": TODAY.isoformat(), "weight": 90})
            archive_id = store.archive_period({"name": "Bulk"})
            frozen = store.archive(archive_id)
            self.assertEqual(frozen["entries"][0]["effective_fat_free_mass"], 72)
            self.assertEqual(frozen["entries"][0]["bmr"], 1925.2)
            reopened = Store(Path(directory), lambda: TODAY)
            self.assertEqual(reopened.state()["today_stats"]["bmr"], 2119.6)
            reopened.save_settings({"body_composition_mode": "fat_free_mass"})
            self.assertEqual(reopened.state()["today_stats"]["bmr"], 1601.2)
            self.assertEqual(reopened.settings()["body_fat_percent"], 10)
            self.assertEqual(reopened.archive(archive_id), frozen)
            self.assertEqual(reopened.export()["settings"]["body_composition_mode"], "fat_free_mass")


if __name__ == "__main__":
    unittest.main()
