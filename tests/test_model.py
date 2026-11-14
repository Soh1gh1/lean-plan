from datetime import date, timedelta
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from leanplan.domain import DEFAULT_SETTINGS, ValidationError, build_state, calculate_day, validate_entry, validate_settings
from leanplan.store import Store


TODAY = date(2026, 11, 9)
MACROS = {"protein": 150, "fat": 60, "carbs": 200}


def entry(day, **values):
    return validate_entry({"date": day, **values}, today=TODAY, historical=True)


class EnergyModelTests(unittest.TestCase):
    def setUp(self):
        self.settings = validate_settings({"sex": "male", "age": 22, "height": 173})

    def test_calories_tef_bmr_training_and_deficit_follow_formulas(self):
        result = calculate_day(entry(TODAY.isoformat(), weight=80, training_minutes=40, steps_kcal=100, **MACROS), self.settings, 80)
        self.assertEqual(result["calories"], 1940)
        self.assertEqual(result["tef"], 220.8)
        self.assertEqual(result["bmr"], 1776.25)
        self.assertEqual(result["training_kcal"], 70)
        self.assertEqual(result["tdee"], 2167.05)
        self.assertEqual(result["deficit"], 227.05)

    def test_workbook_tef_formula_with_its_original_macro_values(self):
        result = calculate_day(entry(TODAY.isoformat(), protein=150, carbs=0, fat=15), self.settings, 80)
        self.assertEqual(result["tef"], 152.7)
        self.assertEqual(result["calories"], 735)

    def test_empty_macros_are_unknown_and_explicit_zero_is_recorded(self):
        result = calculate_day(entry(TODAY.isoformat(), weight=80), self.settings, 80)
        self.assertIsNone(result["calories"])
        self.assertIsNone(result["tef"])
        self.assertIsNone(result["deficit"])
        self.assertEqual(result["bmr"], 1776.25)
        zeros = calculate_day(entry(TODAY.isoformat(), protein=0, carbs=0, fat=0), self.settings, 80)
        self.assertEqual(zeros["calories"], 0)
        self.assertEqual(zeros["tef"], 0)
        self.assertEqual(zeros["deficit"], zeros["tdee"])

    def test_each_macro_calculates_independently_without_filling_blank_fields(self):
        cases = [({"protein": 150}, 600, 150), ({"carbs": 200}, 800, 60),
                 ({"fat": 60}, 540, 10.8), ({"protein": 150, "fat": 60}, 1140, 160.8),
                 ({"carbs": 200, "fat": 60}, 1340, 70.8), ({"protein": 0}, 0, 0)]
        for macros, calories, tef in cases:
            with self.subTest(macros=macros):
                result = calculate_day(entry(TODAY.isoformat(), **macros), self.settings, 80)
                self.assertEqual(result["calories"], calories)
                self.assertEqual(result["tef"], tef)
                self.assertEqual(result["deficit"], round(1776.25 + tef - calories, 3))
                for key in {"protein", "carbs", "fat"} - macros.keys():
                    self.assertIsNone(result[key])

    def test_weekly_measurements_never_fill_missing_raw_weights_or_weight_samples(self):
        rows = [entry((TODAY-timedelta(days=21-i)).isoformat(),
                      weight={0:82, 7:81.5, 14:81.5}.get(i), **MACROS) for i in range(22)]
        state = build_state(rows, self.settings, TODAY)
        measured = [row for row in state["entries"] if row["weight"] is not None]
        self.assertEqual(len(measured), 3)
        self.assertEqual(state["summary"]["weight_count"], 3)
        self.assertEqual(state["summary"]["latest_weight"], 81.5)
        self.assertEqual(state["summary"]["latest_weight_date"], (TODAY-timedelta(days=7)).isoformat())
        self.assertIsNone(state["today_stats"]["weight"])
        self.assertEqual(state["today_stats"]["effective_weight"], 81.5)
        self.assertEqual(state["today_stats"]["bmr"], 1791.25)
        self.assertIsNone(state["summary"]["recent_average"])
        self.assertEqual(measured[1]["weight_average_samples"], 1)

    def test_daily_macros_never_carry_forward_or_use_old_profile_values(self):
        old_settings = {**self.settings, "tef_mode": "macros", "protein": 900, "fat": 900, "carbs": 900}
        rows = [entry("2026-11-08", weight=80, **MACROS), entry("2026-11-09", weight=79.9)]
        state = build_state(rows, old_settings, TODAY)
        self.assertEqual(state["entries"][0]["tef"], 220.8)
        self.assertIsNone(state["today_stats"]["tef"])
        self.assertIsNone(state["today_stats"]["calories"])
        self.assertEqual(state["summary"]["deficit_days"], 1)

    def test_history_uses_only_weight_known_on_or_before_that_date(self):
        rows = [entry("2026-11-01", **MACROS), entry("2026-11-02", weight=80),
                entry("2026-11-03", **MACROS), entry("2026-11-04", weight=79)]
        result = build_state(rows, self.settings, TODAY)["entries"]
        self.assertIsNone(result[0]["tdee"])
        self.assertEqual(result[2]["effective_weight"], 80)
        self.assertEqual(result[2]["weight_source_date"], "2026-11-02")
        self.assertNotEqual(result[2]["bmr"], result[3]["bmr"])

    def test_today_and_all_time_balances_are_independent_and_signed(self):
        rows = [entry("2026-11-08", weight=80, protein=200, fat=100, carbs=300),
                entry("2026-11-09", weight=80, **MACROS)]
        state = build_state(rows, self.settings, TODAY)
        self.assertLess(state["entries"][0]["deficit"], 0)
        self.assertGreater(state["today_stats"]["deficit"], 0)
        self.assertLess(state["summary"]["total_deficit"], 0)
        self.assertAlmostEqual(state["summary"]["total_deficit"], sum(row["deficit"] for row in state["entries"]))

    def test_computed_calorie_key_and_future_dates_are_rejected(self):
        self.assertEqual(validate_entry({"date":"2026-11-08","weight":80},TODAY)["weight"],80)
        with self.assertRaises(ValidationError):
            validate_entry({"date":"2026-11-10","weight":80},TODAY)
        with self.assertRaises(ValidationError):
            validate_entry({"date": TODAY.isoformat(), "calories": 2000}, TODAY)

    def test_steps_do_not_silently_turn_into_calories(self):
        base = calculate_day(entry(TODAY.isoformat(), steps=12000, **MACROS), self.settings, 80)
        walking = calculate_day(entry(TODAY.isoformat(), steps_kcal=80, **MACROS), self.settings, 80)
        self.assertAlmostEqual(walking["tdee"] - base["tdee"], 80)

    def test_trend_requires_measurements_in_both_calendar_windows(self):
        sparse = build_state([entry("2026-10-01", weight=85), entry(TODAY.isoformat(), weight=80)], self.settings, TODAY)
        self.assertIsNone(sparse["summary"]["trend_change"])
        self.assertEqual(sparse["entries"][-1]["weight_average_samples"], 1)
        rows = [entry((TODAY-timedelta(days=i)).isoformat(), weight=80 if i<7 else 81) for i in (0,2,6,7,9,13)]
        self.assertEqual(build_state(rows, self.settings, TODAY)["summary"]["trend_change"], -1)

    def test_goal_progress_handles_loss_gain_and_equal_start(self):
        rows = [entry("2026-11-01", weight=80), entry(TODAY.isoformat(), weight=78)]
        for goal, expected in ((76,50), (84,0), (80,0)):
            self.assertEqual(build_state(rows, {**self.settings,"goal_weight":goal}, TODAY)["summary"]["goal_progress"], expected)

    def test_validation_rejects_invalid_macros_and_preserves_decimal_values(self):
        for values in ({"protein":float("nan")}, {"fat":float("inf")}, {"carbs":-1}, {"weight":True}, {"steps":1.5}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                entry(TODAY.isoformat(), **values)
        self.assertEqual(entry(TODAY.isoformat(), protein="150,5",fat=60,carbs=200)["calories"], 1942)

    def test_settings_strip_removed_targets_and_tef_modes(self):
        settings = validate_settings({"calorie_target":2000,"protein":150,"tef_mode":"fixed","tef_fixed":200}, {"calorie_target":1000})
        self.assertEqual(set(settings), set(DEFAULT_SETTINGS))
        self.assertEqual(settings["training_met"], 2.25)


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.day = TODAY
        self.store = Store(Path(self.temp.name), lambda:self.day)

    def tearDown(self):
        self.temp.cleanup()

    def test_new_database_and_skipped_onboarding_are_empty(self):
        self.assertEqual(self.store.entries(), [])
        self.assertIsNone(self.store.settings()["age"])
        self.store.onboard({"settings":{}})
        self.assertTrue(self.store.settings()["onboarding_done"])
        self.assertEqual(self.store.entries(), [])
        self.assertEqual(self.store.settings()["training_met"], 2.25)

    def test_same_day_updates_reopen_and_delete(self):
        self.store.save_entry({"date":TODAY.isoformat(),"weight":80,**MACROS})
        self.store.save_entry({"date":TODAY.isoformat(),"weight":79.9,"protein":160,"fat":60,"carbs":200})
        reopened = Store(Path(self.temp.name), lambda:self.day)
        self.assertEqual(len(reopened.entries()), 1)
        self.assertEqual(reopened.entries()[0]["calories"], 1980)
        reopened.delete_entry(TODAY.isoformat())
        self.assertEqual(reopened.entries(), [])

    def test_late_entries_are_permanent_and_future_saves_are_rejected(self):
        self.store.save_entry({"date":TODAY.isoformat(),"weight":80})
        past=(TODAY-timedelta(days=1)).isoformat()
        self.store.save_entry({"date":past,"weight":79})
        self.assertEqual(self.store.entries()[0]["entered_late"],1)
        self.store.save_entry({"date":past,"protein":150,"entered_late":0})
        self.assertEqual(self.store.entries()[0]["entered_late"],1)
        self.assertEqual(self.store.entries()[0]["first_recorded_on"],TODAY.isoformat())
        with self.assertRaises(ValidationError):
            self.store.save_entry({"date":(TODAY+timedelta(days=1)).isoformat(),"weight":70})
        self.assertEqual(self.store.entries()[-1]["weight"],80)

    def test_rollover_starts_with_empty_macros_and_previous_weight(self):
        self.store.save_settings({"sex":"male","age":22,"height":173})
        self.store.save_entry({"date":TODAY.isoformat(),"weight":80,**MACROS})
        self.day += timedelta(days=1)
        state = self.store.state()
        self.assertEqual(state["today"], self.day.isoformat())
        self.assertIsNone(state["today_stats"]["calories"])
        self.assertIsNone(state["today_stats"]["tef"])
        self.assertEqual(state["today_stats"]["bmr"], 1776.25)
        self.store.save_entry({"date":TODAY.isoformat(),"weight":79})
        self.assertEqual(self.store.entries()[0]["entered_late"],1)
        self.store.save_entry({"date":self.day.isoformat(),**MACROS})
        self.assertEqual(len(self.store.entries()), 2)

    def test_autosave_patches_preserve_other_fields_and_blanks_are_unknown(self):
        day=TODAY.isoformat()
        self.store.save_settings({"sex":"male","age":22,"height":173})
        self.store.save_entry({"date":day,"weight":80,"training_minutes":40,"note":"Keep me",**MACROS})
        self.store.save_entry({"date":day,"protein":160})
        row=self.store.entries()[0]
        self.assertEqual(row["fat"],60)
        self.assertEqual(row["training_minutes"],40)
        self.assertEqual(row["note"],"Keep me")
        self.store.save_entry({"date":day,"protein":None})
        self.assertEqual(self.store.state()["today_stats"]["calories"],1340)
        self.assertEqual(self.store.state()["summary"]["total_deficit"],577.05)
        self.assertIsNone(self.store.entries()[0]["protein"])
        self.store.save_entry({"date":day,"weight":None,"fat":None,"carbs":None,"training_minutes":None,"note":""})
        self.assertFalse(self.store.state()["entries"][0]["has_data"])
        self.assertEqual(self.store.state()["summary"]["entry_count"],0)
        self.assertIsNone(self.store.state()["today_stats"]["calories"])
        self.assertIsNone(self.store.state()["summary"]["total_deficit"])

    def test_single_macro_survives_reopening_and_clears_without_recording_zeros(self):
        self.store.save_entry({"date":TODAY.isoformat(),"protein":150})
        reopened=Store(Path(self.temp.name),lambda:self.day)
        self.assertEqual(reopened.entries()[0]["calories"],600)
        self.assertEqual(reopened.state()["today_stats"]["tef"],150)
        self.assertIsNone(reopened.entries()[0]["fat"])
        self.assertIsNone(reopened.entries()[0]["carbs"])
        reopened.save_entry({"date":TODAY.isoformat(),"protein":None})
        self.assertIsNone(reopened.state()["today_stats"]["calories"])
        self.assertIsNone(reopened.state()["summary"]["average_calories"])
        self.assertEqual(reopened.state()["summary"]["calorie_count"],0)

    def test_missing_activity_is_not_a_recorded_zero(self):
        self.store.save_settings({"sex":"male","age":22,"height":173})
        self.store.save_entry({"date":TODAY.isoformat(),"weight":80,**MACROS})
        result=self.store.state()["today_stats"]
        self.assertIsNone(result["training_kcal"])
        self.assertIsNone(result["steps_kcal"])
        self.assertEqual(result["deficit"],57.05)
        self.store.save_entry({"date":TODAY.isoformat(),"training_minutes":0,"steps_kcal":0})
        result=self.store.state()["today_stats"]
        self.assertEqual(result["training_kcal"],0)
        self.assertEqual(result["deficit"],57.05)

    def test_training_default_is_snapshotted_in_daily_record(self):
        self.store.save_entry({"date":TODAY.isoformat(),"weight":80,"training_minutes":40,**MACROS})
        self.day += timedelta(days=1)
        self.store.save_settings({"training_met":4})
        self.assertEqual(self.store.entries()[0]["training_met"], 2.25)
        self.store.save_entry({"date":self.day.isoformat(),"training_minutes":40,**MACROS})
        self.assertEqual(self.store.entries()[1]["training_met"], 4)
        self.store.save_settings({"training_met":3})
        self.assertEqual(self.store.entries()[0]["training_met"],2.25)
        self.assertEqual(self.store.entries()[1]["training_met"],3)

    def test_clear_history_keeps_profile_and_makes_a_complete_safety_copy(self):
        self.store.save_settings({"name":"Test","age":22})
        self.store.save_entry({"date":TODAY.isoformat(),"weight":80,**MACROS})
        self.store.clear_history()
        self.assertEqual(self.store.entries(), [])
        self.assertEqual(self.store.settings()["name"], "Test")
        snapshots = list((Path(self.temp.name)/"backups").glob('*.sqlite3'))
        self.assertTrue(any(self.snapshot_count(path)==1 for path in snapshots))

    @staticmethod
    def snapshot_count(path):
        with closing(sqlite3.connect(path)) as db:
            return db.execute('SELECT count(*) FROM entries').fetchone()[0]

    def test_onboarding_does_not_overwrite_today_macros_or_notes(self):
        self.store.save_entry({"date":TODAY.isoformat(),"note":"Keep me",**MACROS})
        with self.assertRaises(ValidationError):
            self.store.onboard({"settings":{"age":30},"weight":-2})
        self.assertIsNone(self.store.settings()["age"])
        self.store.onboard({"settings":{"age":30},"weight":80})
        self.assertEqual(self.store.entries()[0]["protein"], 150)
        self.assertEqual(self.store.entries()[0]["note"], "Keep me")

    def test_old_database_is_migrated_without_inventing_daily_macros(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"leanplan.sqlite3"
            with closing(sqlite3.connect(path)) as db:
                db.executescript('CREATE TABLE settings(id INTEGER PRIMARY KEY,value TEXT); CREATE TABLE entries(date TEXT PRIMARY KEY,weight REAL,calories REAL,training_minutes REAL,training_met REAL,steps INTEGER,steps_kcal REAL,note TEXT,created_at TEXT,updated_at TEXT);')
                db.execute('INSERT INTO settings VALUES(1,?)',(json.dumps({"sex":"male","age":22,"height":173,"tef_mode":"macros","protein":150,"fat":15,"carbs":0}),))
                db.execute("INSERT INTO entries VALUES('2026-11-08',80,2000,NULL,NULL,NULL,NULL,'Old record','','')")
                db.commit()
            migrated = Store(Path(folder), lambda:TODAY)
            self.assertEqual(migrated.entries()[0]["calories"], 2000)
            self.assertIsNone(migrated.entries()[0]["protein"])
            self.assertIsNone(migrated.state()["entries"][0]["calories"])
            self.assertNotIn("tef_mode", migrated.settings())
            self.assertTrue(list((Path(folder)/'backups').glob('*.sqlite3')))


if __name__ == '__main__':
    unittest.main()
