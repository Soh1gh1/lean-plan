"""Manual calorie precedence, blank/zero semantics, migration and frozen archives."""
import csv
from datetime import date, timedelta
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen

from leanplan.domain import ValidationError, build_state, calculate_day, validate_entry, validate_settings
from leanplan.server import create_server
from leanplan.store import Store


TODAY = date(2026, 11, 14)
PROFILE = {"age": 35, "height": 180, "sex": "male"}
MACROS = {"protein": 150, "carbs": 200, "fat": 60}


class ManualCalorieTests(unittest.TestCase):
    def calculate(self, **values):
        row = validate_entry({"date": TODAY.isoformat(), **MACROS, **values}, TODAY)
        return calculate_day(row, validate_settings(PROFILE), 80)

    def test_independent_food_example_changes_intake_but_not_tef_or_expenditure(self):
        macros = {"protein": 178.42, "fat": 28.98, "carbs": 0}
        automatic = self.calculate(**macros)
        manual = self.calculate(**macros, calorie_override=1020)
        self.assertEqual(automatic["calories"], 974.5)
        self.assertEqual(automatic["calories_source"], "macros")
        self.assertEqual(manual["calculated_calories"], 974.5)
        self.assertEqual(manual["calories"], 1020)
        self.assertEqual(manual["calories_source"], "manual")
        self.assertEqual(manual["tef"], 183.636)
        self.assertEqual(manual["tdee"], automatic["tdee"])
        self.assertAlmostEqual(manual["deficit"]-automatic["deficit"], -45.5)

    def test_zero_is_a_manual_value_and_empty_restores_the_formula(self):
        zero = self.calculate(calorie_override=0)
        self.assertEqual(zero["calories"], 0)
        self.assertEqual(zero["calories_source"], "manual")
        self.assertEqual(zero["calculated_calories"], 1940)
        for empty in (None, ""):
            result = self.calculate(calorie_override=empty)
            self.assertEqual(result["calories"], 1940)
            self.assertEqual(result["calories_source"], "macros")

    def test_manual_only_does_not_create_macros_or_tef_and_counts_in_statistics(self):
        row = validate_entry({"date": TODAY.isoformat(), "calorie_override": 0}, TODAY)
        state = build_state([row], validate_settings(PROFILE), TODAY,
                            baseline={"weight": 80, "date": "2026-11-01"})
        current = state["today_stats"]
        for key in ("protein", "fat", "carbs", "tef", "calculated_calories"):
            self.assertIsNone(current[key])
        self.assertEqual(current["calories"], 0)
        self.assertEqual(state["summary"]["average_calories"], 0)
        self.assertEqual(state["summary"]["total_deficit"], 1755)
        self.assertEqual(state["summary"]["calorie_count"], 1)
        self.assertEqual(state["summary"]["entry_count"], 1)
        self.assertEqual(state["summary"]["weight_count"], 0)
        self.assertEqual(state["summary"]["streak"], 1)
        row["calorie_override"] = None
        cleared = build_state([row], validate_settings(PROFILE), TODAY)
        self.assertIsNone(cleared["today_stats"]["calories"])
        self.assertIsNone(cleared["summary"]["average_calories"])
        self.assertEqual(cleared["summary"]["entry_count"], 0)

    def test_manual_value_stays_fixed_when_macros_change_and_tef_still_changes(self):
        first = self.calculate(calorie_override=1020)
        changed = self.calculate(calorie_override=1020, protein=160)
        self.assertEqual(changed["calories"], 1020)
        self.assertEqual(changed["calculated_calories"], 1980)
        self.assertEqual(changed["tef"], 230.8)
        self.assertAlmostEqual(changed["deficit"]-first["deficit"], 10)

    def test_validation_and_decimal_input(self):
        self.assertEqual(self.calculate(calorie_override="1020,5")["calories"], 1020.5)
        for value in (-1, 50001, True, "nan", "inf", "text"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.calculate(calorie_override=value)

    def test_patch_roundtrip_and_json_export_ignore_stale_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory), lambda: TODAY)
            store.save_entry({"date": TODAY.isoformat(), **MACROS, "calorie_override": 1020})
            store.save_entry({"date": TODAY.isoformat(), "protein": 160})
            self.assertEqual(store.entries()[0]["calorie_override"], 1020)
            with store.connect() as db:
                db.execute("UPDATE entries SET calories=999")
            exported = store.export()["entries"][0]
            self.assertEqual(exported["calories"], 1020)
            self.assertEqual(exported["calculated_calories"], 1980)
            self.assertEqual(exported["calories_source"], "manual")
            reopened = Store(Path(directory), lambda: TODAY)
            self.assertEqual(reopened.state()["today_stats"]["calories"], 1020)
            reopened.save_entry({"date": TODAY.isoformat(), "calorie_override": None})
            self.assertEqual(reopened.state()["today_stats"]["calories"], 1980)
            self.assertEqual(reopened.entries()[0]["carbs"], 200)

    def test_migration_backs_up_and_does_not_turn_legacy_cache_into_manual_calories(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory), lambda: TODAY)
            store.save_entry({"date": TODAY.isoformat(), **MACROS})
            with store.connect() as db:
                db.execute("ALTER TABLE entries DROP COLUMN calorie_override")
                db.execute("UPDATE entries SET calories=999")
            migrated = Store(Path(directory), lambda: TODAY)
            self.assertIsNone(migrated.entries()[0]["calorie_override"])
            self.assertEqual(migrated.entries()[0]["calories"], 999)
            self.assertEqual(migrated.state()["today_stats"]["calories"], 1940)
            backed_up_old_schema = False
            for backup in (Path(directory)/"backups").glob("*.sqlite3"):
                db = sqlite3.connect(backup)
                try:
                    columns = {column[1] for column in db.execute("PRAGMA table_info(entries)")}
                    if "calorie_override" not in columns:
                        backed_up_old_schema = True
                        self.assertEqual(db.execute("SELECT calories FROM entries").fetchone()[0], 999)
                finally:
                    db.close()
            self.assertTrue(backed_up_old_schema)

    def test_archives_freeze_manual_values_and_current_totals_remain_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory), lambda: TODAY)
            store.save_settings(PROFILE)
            yesterday = (TODAY-timedelta(days=1)).isoformat()
            store.save_entry({"date": yesterday, "weight": 80, **MACROS, "calorie_override": 1020})
            store.save_entry({"date": TODAY.isoformat(), **MACROS})
            archive_id = store.archive_period({"name": "Cut"})
            frozen = store.archive(archive_id)
            self.assertEqual(frozen["entries"][0]["calories"], 1020)
            self.assertEqual(frozen["entries"][0]["calculated_calories"], 1940)
            self.assertEqual(frozen["entries"][0]["calories_source"], "manual")
            self.assertEqual(store.state()["summary"]["average_calories"], 1940)
            store.save_settings({"age": 40})
            store.save_entry({"date": TODAY.isoformat(), "calorie_override": 1100})
            self.assertEqual(store.archive(archive_id), frozen)
            with self.assertRaises(ValidationError):
                store.save_entry({"date": yesterday, "calorie_override": None})

    def test_http_and_csv_report_effective_calories_formula_value_and_source(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory), lambda: TODAY)
            server = create_server(store, Path(__file__).resolve().parents[1]/"static")
            threading.Thread(target=server.serve_forever, daemon=True).start()
            url = f"http://127.0.0.1:{server.server_port}"
            try:
                with urlopen(url+"/api/state") as response:
                    token = json.load(response)["token"]
                payload = {"date": TODAY.isoformat(), **MACROS, "calorie_override": 1020, "note": "=SUM(1;2)"}
                request = Request(url+"/api/entry", json.dumps(payload).encode(),
                                  headers={"X-Leanplan-Token": token, "Content-Type": "application/json"})
                with urlopen(request) as response:
                    self.assertEqual(json.load(response)["today_stats"]["calories"], 1020)
                with urlopen(url+"/api/export/csv") as response:
                    rows = list(csv.DictReader(StringIO(response.read().decode("utf-8-sig")), delimiter=";"))
                self.assertEqual(float(rows[0]["Calories, kcal"]), 1020)
                self.assertEqual(float(rows[0]["Calculated calories, kcal"]), 1940)
                self.assertEqual(float(rows[0]["Manual calories, kcal"]), 1020)
                self.assertEqual(rows[0]["Calories source"], "manual")
                self.assertTrue(rows[0]["Note"].startswith("'="))
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
