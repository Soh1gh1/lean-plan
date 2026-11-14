"""Compare both calculation engines over deterministic edge cases and journals.

All data is synthetic and temporary. The user's database is never opened.
"""
from datetime import date, timedelta
import json
import math
from pathlib import Path
import random
import tempfile
import threading

from playwright.sync_api import sync_playwright

from leanplan.domain import build_state, calculate_day, validate_entry, validate_settings
from leanplan.server import create_server
from leanplan.store import Store


ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 11, 14)
DAILY_FIELDS = ('calories', 'tef', 'bmr', 'training_kcal', 'training_met_used', 'tdee',
                'deficit', 'effective_weight', 'has_data', 'bmr_formula',
                'calorie_override', 'calculated_calories', 'calories_source')
SUMMARY_FIELDS = ('entry_count', 'weight_count', 'calorie_count', 'latest_weight',
                  'latest_weight_date', 'start_weight', 'start_date', 'weight_change',
                  'average_calories', 'total_deficit', 'deficit_days', 'recent_average',
                  'previous_average', 'recent_samples', 'previous_samples',
                  'trend_change', 'goal_progress')


def main():
    rng = random.Random(14062026)
    cases = []
    profile = {'age': 35, 'height': 180, 'sex': 'male'}
    control = {'date': TODAY.isoformat(), 'weight': 80, 'protein': 150, 'carbs': 200,
               'fat': 60, 'training_minutes': 45, 'training_met': 4, 'steps': 12000,
               'steps_kcal': 250}
    for setting_patch in ({}, {'sex': 'female'}, {'sex': None}, {'age': None}, {'height': None},
                          {'fat_free_mass': 57},
                          {'body_composition_mode': 'body_fat', 'body_fat_percent': 10, 'fat_free_mass': 57},
                          {'fat_free_mass': 57, 'age': None, 'height': None, 'sex': None}):
        for entry_patch in ({}, {'weight': None}, {'protein': None, 'fat': None, 'carbs': None},
                            {'protein': 0, 'fat': None, 'carbs': None},
                            {'training_minutes': 0}, {'training_met': 1},
                            {'calorie_override': 1020}, {'calorie_override': 0},
                            {'calorie_override': 50000},
                            {'protein': None, 'fat': None, 'carbs': None, 'calorie_override': 1100}):
            settings = {**validate_settings(profile), **setting_patch}
            row = validate_entry({**control, **entry_patch}, TODAY)
            cases.append({'settings': settings, 'entry': row, 'weight': row['weight']})
    for _ in range(500):
        settings = validate_settings({'sex': rng.choice(['male', 'female', None]),
                                      'age': rng.choice([None, rng.randint(18, 100)]),
                                      'height': rng.choice([None, round(rng.uniform(120, 220), 3)])})
        row = validate_entry({'date': TODAY.isoformat(),
                              'weight': rng.choice([None, round(rng.uniform(40, 180), 4)]),
                              'protein': rng.choice([None, 0, round(rng.uniform(0, 300), 3)]),
                              'fat': rng.choice([None, 0, round(rng.uniform(0, 180), 3)]),
                              'carbs': rng.choice([None, 0, round(rng.uniform(0, 500), 3)]),
                              'calorie_override': rng.choice([None, None, 0, 1020, round(rng.uniform(500, 5000), 3)]),
                              'training_minutes': rng.choice([None, 0, round(rng.uniform(0, 240), 3)]),
                              'training_met': rng.choice([None, 1, 2.25, 3.5, 6, 10]),
                              'steps': rng.choice([None, 0, 10000]),
                              'steps_kcal': rng.choice([None, 0, round(rng.uniform(0, 1000), 3)])}, TODAY)
        cases.append({'settings': settings, 'entry': row, 'weight': row['weight']})

    fixtures = []
    for index in range(120):
        settings = validate_settings({'sex': rng.choice(['male', 'female', None]),
                                      'age': 35, 'height': 180, 'goal_weight': rng.choice([None, 70, 80, 90])})
        baseline = {'weight': 80, 'date': (TODAY-timedelta(days=40)).isoformat()} if index % 3 == 0 else None
        rows = []
        for days_ago in range(30, -1, -1):
            if rng.random() < .2:
                continue
            rows.append(validate_entry({'date': (TODAY-timedelta(days=days_ago)).isoformat(),
                                        'weight': rng.choice([None, None, None, round(rng.uniform(70, 90), 3)]),
                                        'protein': rng.choice([None, 0, 150, 150.125]),
                                        'carbs': rng.choice([None, 0, 200, 200.625]),
                                        'fat': rng.choice([None, 0, 60, 60.375]),
                                        'calorie_override': rng.choice([None, None, 0, 1020, 1940.125]),
                                        'training_minutes': rng.choice([None, 0, 45, 60]),
                                        'training_met': rng.choice([None, 2.25, 3.5, 6]),
                                        'steps_kcal': rng.choice([None, 0, 100, 200.125])}, TODAY))
        fixtures.append({'today': TODAY.isoformat(), 'settings': settings, 'entries': rows, 'baseline': baseline})

    mismatches = []
    comparisons = 0

    def compare(expected, actual, fields, location):
        nonlocal comparisons
        for key in fields:
            comparisons += 1
            left, right = expected.get(key), actual.get(key)
            same = math.isclose(left, right, rel_tol=0, abs_tol=1e-9) if isinstance(left, (int, float)) and not isinstance(left, bool) and isinstance(right, (int, float)) else left == right
            if not same:
                mismatches.append({'location': location, 'field': key, 'python': left, 'screen': right})

    with tempfile.TemporaryDirectory() as folder:
        store = Store(Path(folder), lambda: TODAY)
        store.save_settings({'onboarding_done': True})
        server = create_server(store, ROOT/'static')
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe', headless=True)
                page = browser.new_page()
                page.goto(f'http://127.0.0.1:{server.server_port}')
                page.get_by_role('heading', name='Overview', exact=True).wait_for()
                actual = page.evaluate('(cases)=>cases.map(c=>calculate(c.entry,c.settings,c.weight,null))', cases)
                for index, (case, row) in enumerate(zip(cases, actual)):
                    compare(calculate_day(case['entry'], case['settings'], case['weight']), row, DAILY_FIELDS, f'day:{index}')
                states = page.evaluate('''(fixtures)=>fixtures.map(f=>{base={...base,...f};drafts.clear();rebuild();return state;})''', fixtures)
                for index, (fixture, actual) in enumerate(zip(fixtures, states)):
                    expected = build_state(fixture['entries'], fixture['settings'], TODAY, baseline=fixture['baseline'])
                    compare(expected['summary'], actual['summary'], SUMMARY_FIELDS, f'summary:{index}')
                    compare(expected['today_stats'], actual['today_stats'], DAILY_FIELDS+('weight_source_date',), f'today:{index}')
                    for left, right in zip(expected['entries'], actual['entries']):
                        compare(left, right, DAILY_FIELDS+('date', 'weight', 'weight_source_date', 'weight_average', 'weight_average_samples'), f'journal:{index}:{left["date"]}')
                rounding = [.0625, -.0625, .0005, -.0005, .0015, -.0015, 100.1235, -100.1235]
                from leanplan.domain import rounded
                for value, actual in zip(rounding, page.evaluate('(values)=>values.map(round)', rounding)):
                    compare({'rounded': rounded(value)}, {'rounded': actual}, ('rounded',), f'rounding:{value}')
                browser.close()
        finally:
            server.shutdown()
            server.server_close()

    output = ROOT/'test-results'/'calculation-audit.json'
    output.parent.mkdir(exist_ok=True)
    report = {'result': 'passed' if not mismatches else 'failed', 'daily_cases': len(cases),
              'journal_cases': len(fixtures), 'field_comparisons': comparisons,
              'mismatch_count': len(mismatches), 'mismatches': mismatches}
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({**report, 'mismatches': mismatches[:12], 'report': str(output)}))
    assert not mismatches, f'{len(mismatches)} calculation differences; inspect {output}'


if __name__ == '__main__':
    main()
