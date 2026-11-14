"""Independent control examples, input dependencies and reporting consistency."""
import csv
from datetime import date, timedelta
from io import StringIO
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.request import urlopen

from leanplan.domain import (ValidationError, build_state, calculate_day, rounded,
                             validate_entry, validate_settings)
from leanplan.server import create_server
from leanplan.store import Store


TODAY = date(2026, 11, 14)
PROFILE = {'sex': 'male', 'age': 35, 'height': 180}
VALUES = {'date': TODAY.isoformat(), 'weight': 80, 'protein': 150, 'fat': 60,
          'carbs': 200, 'training_minutes': 45, 'training_met': 4,
          'steps': 12000, 'steps_kcal': 250}


class CalculationAuditTests(unittest.TestCase):
    def calculate(self, profile=None, values=None, weight=80):
        return calculate_day(validate_entry({**VALUES, **(values or {})}, TODAY),
                             validate_settings({**PROFILE, **(profile or {})}), weight)

    def test_independently_worked_male_and_female_examples(self):
        # 80 kg, 180 cm, 35 y; kcal=600+540+800; TEF=150+10.8+60.
        # Gross exercise=252 kcal, standard resting portion=63, net=189.
        # Male resting energy=800+1125-175+5=1755; female=1589.
        for sex, bmr, expenditure, balance in [('male',1755,2414.8,474.8), ('female',1589,2248.8,308.8)]:
            with self.subTest(sex=sex):
                result = self.calculate({'sex': sex})
                self.assertEqual(result['calories'],1940)
                self.assertEqual(result['tef'],220.8)
                self.assertEqual(result['training_kcal'],189)
                self.assertEqual(result['bmr'],bmr)
                self.assertEqual(result['tdee'],expenditure)
                self.assertEqual(result['deficit'],balance)

    def test_each_required_profile_input_has_the_expected_effect(self):
        base = self.calculate()
        for profile, weight, delta in [({},81,10), ({'height':181},80,6.25),
                                       ({'age':36},80,-5), ({'sex':'female'},80,-166)]:
            with self.subTest(profile=profile,weight=weight):
                result = self.calculate(profile,weight=weight)
                self.assertEqual(result['bmr']-base['bmr'],delta)
                self.assertEqual(result['calories'],base['calories'])
                self.assertEqual(result['tef'],base['tef'])
                if weight==80:
                    self.assertEqual(result['training_kcal'],base['training_kcal'])
                    self.assertAlmostEqual(result['deficit']-base['deficit'],delta)
                else:
                    self.assertEqual(result['training_kcal'],191.363)

    def test_missing_required_data_does_not_invent_a_bmr(self):
        self.assertIsNone(validate_settings({})['sex'])
        for missing in ('age','height','sex'):
            with self.subTest(missing=missing):
                result = self.calculate({missing:None})
                self.assertIsNone(result['bmr'])
                self.assertIsNone(result['tdee'])
                self.assertIsNone(result['deficit'])
                self.assertEqual(result['training_kcal'],189)
                self.assertEqual(result['calories'],1940)
        result = self.calculate(weight=None)
        self.assertIsNone(result['bmr'])
        self.assertIsNone(result['training_kcal'])
        self.assertIsNone(result['tdee'])
        with self.assertRaises(ValidationError):
            validate_settings({'age':17})

    def test_training_uses_weight_duration_met_and_subtracts_standard_rest_once(self):
        for values, weight, kcal in [({'training_minutes':90},80,378),
                                     ({'training_met':2},80,63),
                                     ({'training_met':1},80,0),
                                     ({'training_minutes':0},None,0),
                                     ({'training_minutes':None},80,None)]:
            with self.subTest(values=values,weight=weight):
                self.assertEqual(self.calculate(values=values,weight=weight)['training_kcal'],kcal)
        self.assertEqual(self.calculate(values={'training_met':None})['training_kcal'],78.75)

    def test_manual_active_walking_energy_is_added_once_not_again_from_steps(self):
        base = self.calculate()
        for steps in (None,0,10000,30000):
            self.assertEqual(self.calculate(values={'steps':steps})['tdee'],base['tdee'])
        walking = self.calculate(values={'steps_kcal':500})
        self.assertEqual(walking['tdee']-base['tdee'],250)
        self.assertAlmostEqual(walking['deficit']-base['deficit'],250)
        self.assertEqual(self.calculate(values={'steps_kcal':None})['tdee'],2164.8)

    def test_non_energy_settings_cannot_change_energy_balance(self):
        base = self.calculate()
        for profile in ({'name':'Another name'},{'goal_weight':65},{'onboarding_done':True}):
            result = self.calculate(profile)
            for key in ('bmr','training_kcal','tef','calories','tdee','deficit'):
                self.assertEqual(result[key],base[key])

    def test_each_macro_gram_changes_intake_tef_and_balance_by_its_own_factor(self):
        base=self.calculate()
        for key, calories, tef, balance in [('protein',4,1,-3),('carbs',4,.3,-3.7),('fat',9,.18,-8.82)]:
            with self.subTest(macro=key):
                result=self.calculate(values={key:VALUES[key]+1})
                self.assertEqual(result['calories']-base['calories'],calories)
                self.assertAlmostEqual(result['tef']-base['tef'],tef)
                self.assertAlmostEqual(result['deficit']-base['deficit'],balance)

    def test_signed_totals_and_average_do_not_count_unknown_days_as_zero(self):
        settings = validate_settings(PROFILE)
        rows = [validate_entry({'date':'2026-11-01','weight':80,'protein':100,'fat':50,'carbs':200},TODAY),
                validate_entry({'date':'2026-11-08','protein':200,'fat':100,'carbs':300},TODAY),
                validate_entry({'date':'2026-11-14','training_minutes':45,'training_met':4},TODAY)]
        result = build_state(rows,settings,TODAY)
        self.assertEqual(result['entries'][0]['deficit'],274)
        self.assertEqual(result['entries'][1]['deficit'],-837)
        self.assertIsNone(result['today_stats']['deficit'])
        self.assertEqual(result['summary']['total_deficit'],-563)
        self.assertEqual(result['summary']['average_calories'],2275)
        self.assertEqual(result['summary']['calorie_count'],2)
        self.assertEqual(result['summary']['deficit_days'],2)
        # A deliberate zero intake is a sample; an unknown intake is not.
        rows[2] = validate_entry({'date':TODAY.isoformat(),'protein':0},TODAY)
        result = build_state(rows,settings,TODAY)
        self.assertEqual(result['summary']['average_calories'],1516.667)
        self.assertEqual(result['summary']['calorie_count'],3)

    def test_weekly_change_works_with_one_real_measurement_in_each_week(self):
        rows = [validate_entry({'date':(TODAY-timedelta(days=7)).isoformat(),'weight':80},TODAY),
                validate_entry({'date':TODAY.isoformat(),'weight':79.5},TODAY)]
        result = build_state(rows,validate_settings(PROFILE),TODAY)
        self.assertEqual(result['summary']['trend_change'],-.5)
        self.assertEqual(result['summary']['recent_samples'],1)
        self.assertEqual(result['summary']['previous_samples'],1)
        self.assertEqual(result['summary']['weight_count'],2)

    def test_goal_progress_handles_gain_loss_and_overshoot_without_changing_energy(self):
        for latest, goal, expected in [(82,84,50),(78,76,50),(85,84,100),(79,84,0),(80,80,100),(81,80,0)]:
            with self.subTest(latest=latest,goal=goal):
                rows = [validate_entry({'date':'2026-11-01','weight':80},TODAY),
                        validate_entry({'date':TODAY.isoformat(),'weight':latest},TODAY)]
                result = build_state(rows,validate_settings({**PROFILE,'goal_weight':goal}),TODAY)
                self.assertEqual(result['summary']['goal_progress'],expected)

    def test_rounding_is_symmetric_and_does_not_leave_negative_zero(self):
        self.assertEqual(rounded(.0625),.063)
        self.assertEqual(rounded(-.0625),-.063)
        self.assertEqual(rounded(-.00001),0)
        self.assertEqual(rounded(None),None)

    def test_api_and_exports_recompute_old_cached_calories_without_changing_raw_data(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory),lambda:TODAY)
            store.save_settings(PROFILE)
            store.save_entry({'date':TODAY.isoformat(),'protein':150})
            with store.connect() as db:
                db.execute('UPDATE entries SET calories=999')
            server=create_server(store,Path(__file__).resolve().parents[1]/'static')
            threading.Thread(target=server.serve_forever,daemon=True).start()
            url=f'http://127.0.0.1:{server.server_port}'
            try:
                with urlopen(url+'/api/state') as response:
                    state=json.load(response)
                with urlopen(url+'/api/export/json') as response:
                    exported=json.load(response)
                with urlopen(url+'/api/export/csv') as response:
                    rows=list(csv.reader(StringIO(response.read().decode('utf-8-sig')),delimiter=';'))
                self.assertEqual(state['today_stats']['calories'],600)
                self.assertEqual(exported['entries'][0]['calories'],600)
                self.assertEqual(float(rows[1][5]),600)
                self.assertEqual(store.entries()[0]['calories'],999)
            finally:
                server.shutdown();server.server_close()


if __name__ == '__main__':
    unittest.main()
