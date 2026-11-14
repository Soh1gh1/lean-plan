"""Exercise manual calorie editing and its colors using an isolated journal."""
from datetime import date, timedelta
from pathlib import Path
import json
import tempfile
import threading

from playwright.sync_api import sync_playwright

from leanplan.server import create_server
from leanplan.store import Store


ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 11, 14)


def main():
    output = ROOT/'test-results'/'manual-calories'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        store = Store(Path(folder), lambda: TODAY)
        store.save_settings({'age': 22, 'height': 173, 'sex': 'male', 'onboarding_done': True})
        yesterday = (TODAY-timedelta(days=1)).isoformat()
        store.save_entry({'date': yesterday, 'weight': 80, 'protein': 150, 'carbs': 200, 'fat': 60})
        store.save_entry({'date': TODAY.isoformat(), 'weight': 81, 'protein': 178.42, 'carbs': 0, 'fat': 28.98})
        server = create_server(store, ROOT/'static')
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe', headless=True)
                page = browser.new_page(viewport={'width': 1200, 'height': 780})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{server.server_port}')
                page.get_by_role('heading', name='Overview', exact=True).wait_for()
                calories = page.locator('#today-calories')

                def saved():
                    page.evaluate('() => flushAll()')
                    page.wait_for_selector('#sync-status[data-state=saved]')

                assert calories.input_value() == ''
                assert calories.get_attribute('placeholder') == '975'
                assert page.evaluate('state.today_stats.calories') == 974.5
                normal_color = calories.evaluate('(input)=>getComputedStyle(input).color')
                before = page.evaluate('state.today_stats')
                page.evaluate('window.originalCalorieInput=document.querySelector("#today-calories")')
                calories.fill('1020')
                assert calories.evaluate('(input)=>input===document.activeElement')
                assert page.evaluate('window.originalCalorieInput===document.querySelector("#today-calories")')
                assert calories.evaluate('(input)=>getComputedStyle(input).color') != normal_color
                assert page.evaluate('state.today_stats.calories') == 1020
                assert page.evaluate('state.today_stats.tef') == before['tef']
                assert page.evaluate('state.today_stats.tdee') == before['tdee']
                assert page.evaluate('state.summary.average_calories') == 1480
                assert page.locator('.calorie-empty').is_hidden()
                saved()
                assert store.entries()[-1]['calorie_override'] == 1020
                page.screenshot(path=str(output/'overview-manual.png'))
                page.locator('#today-protein').fill('180')
                assert page.evaluate('state.today_stats.calories') == 1020
                assert page.evaluate('state.today_stats.calculated_calories') == 980.82
                assert calories.get_attribute('placeholder') == '981'
                page.locator('#today-protein').fill('178.42')
                for invalid in ('-1', '50001'):
                    calories.fill(invalid)
                    assert calories.get_attribute('aria-invalid') == 'true'
                    assert page.evaluate('state.today_stats.calories') == 1020
                    assert page.locator('.calorie-empty').is_hidden()
                for value in ('1000', '1100', '1020'):
                    calories.fill(value)
                saved()
                assert store.entries()[-1]['calorie_override'] == 1020
                page.reload()
                page.get_by_role('heading', name='Overview', exact=True).wait_for()
                assert calories.input_value() == '1020'
                assert 'manual-value' in calories.get_attribute('class')
                calories.fill('0')
                assert page.evaluate('state.today_stats.calories') == 0
                assert page.evaluate('state.today_stats.calories_source') == 'manual'
                assert page.locator('.calorie-empty').is_hidden()
                saved()
                calories.fill('')
                assert page.evaluate('state.today_stats.calories') == 974.5
                assert calories.evaluate('(input)=>getComputedStyle(input).color') == normal_color
                saved()
                assert store.entries()[-1]['calorie_override'] is None
                page.screenshot(path=str(output/'overview-automatic.png'))
                for macro in ('protein', 'carbs', 'fat'):
                    page.locator(f'#today-{macro}').fill('')
                assert page.evaluate('state.today_stats.calories') is None
                assert page.locator('.calorie-empty').is_visible()
                calories.fill('1020')
                assert page.evaluate('state.today_stats.tef') is None
                assert page.locator('.calorie-empty').is_hidden()
                saved()
                assert all(store.entries()[-1][macro] is None for macro in ('protein', 'carbs', 'fat'))
                for macro, value in (('protein', '178.42'), ('carbs', '0'), ('fat', '28.98')):
                    page.locator(f'#today-{macro}').fill(value)
                saved()

                page.get_by_role('link', name='Daily journal', exact=True).click()
                today_row = page.locator(f'[data-day-cell="{TODAY.isoformat()}"]')
                assert '1,020' in today_row.locator('.manual-value').inner_text()
                today_row.click()
                day_calories = page.locator('#day-calories')
                assert day_calories.input_value() == '1020'
                page.evaluate('window.originalDayCalorieInput=document.querySelector("#day-calories")')
                day_calories.fill('1030')
                assert day_calories.evaluate('(input)=>input===document.activeElement')
                assert page.evaluate('window.originalDayCalorieInput===document.querySelector("#day-calories")')
                saved()
                assert store.entries()[-1]['calorie_override'] == 1030
                day_calories.fill('1020')
                saved()
                page.screenshot(path=str(output/'day-manual.png'))
                page.get_by_role('button', name='Close', exact=True).click()
                page.get_by_role('button', name=f'Open {yesterday}', exact=True).click()
                page.locator('#day-calories').fill('2200')
                saved()
                page.get_by_role('button', name='Close', exact=True).click()
                page.screenshot(path=str(output/'journal-manual.png'))
                page.get_by_role('link', name='Insights', exact=True).click()
                page.get_by_role('tab', name='Calories', exact=True).click()
                assert page.locator('.manual-bar').count() == 2
                assert page.locator('.manual-bar.late-bar').count() == 1
                assert 'Manual' in page.locator('#insight-legend').inner_text()
                page.screenshot(path=str(output/'insights-manual.png'))

                page.get_by_role('link', name='Daily journal', exact=True).click()
                page.get_by_role('button', name='Archive period', exact=True).click()
                page.locator('#archive-name').fill('Manual calorie test')
                page.get_by_role('button', name='Archive & start new', exact=True).click()
                page.wait_for_selector('[role=dialog]', state='detached')
                archive_id = store.state()['archives'][0]['id']
                frozen = store.archive(archive_id)
                page.locator('#journal-period').select_option(str(archive_id))
                page.wait_for_function('() => archiveView !== null')
                page.get_by_role('button', name=f'Open {yesterday}', exact=True).click()
                assert day_calories.is_disabled()
                assert day_calories.input_value() == '2200'
                assert 'manual-value' in day_calories.get_attribute('class')
                page.screenshot(path=str(output/'archive-manual.png'))
                assert store.archive(archive_id) == frozen
                assert store.state()['summary']['average_calories'] == 1020
                assert not errors, errors
                browser.close()
                print(json.dumps({'result': 'passed', 'screenshots': str(output), 'browser_errors': errors,
                                  'checks': ['instant manual override', 'TEF independence', 'stable input focus',
                                             'manual colors', 'blank restores formula', 'zero remains recorded',
                                             'manual-only intake', 'reload persistence', 'journal editing',
                                             'chart source colors', 'read-only archived manual values']}))
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    main()
