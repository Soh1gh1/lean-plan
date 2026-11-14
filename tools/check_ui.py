"""End-to-end autosave checks with a temporary journal and injected calendar."""
from datetime import date, timedelta
import csv
import json
from pathlib import Path
import random
import tempfile
import threading
import time

from playwright.sync_api import sync_playwright

from leanplan.server import create_server
from leanplan.store import Store


ROOT=Path(__file__).resolve().parents[1]


def main():
    output=ROOT/'test-results'
    output.mkdir(exist_ok=True)
    actual_today=date.today()
    clock=[actual_today]
    with tempfile.TemporaryDirectory() as directory:
        store=Store(Path(directory),lambda:clock[0])
        server=create_server(store,ROOT/'static')
        threading.Thread(target=server.serve_forever,daemon=True).start()
        url=f'http://127.0.0.1:{server.server_port}'
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
                context=browser.new_context(viewport={'width':1440,'height':1000},accept_downloads=True,color_scheme='light')
                page=context.new_page()
                errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)))

                def saved():
                    page.evaluate('() => flushAll()')
                    page.wait_for_selector('#sync-status[data-state=saved]')

                page.goto(url)
                page.get_by_role('heading',name='Your profile',exact=True).wait_for()
                assert page.locator('[role=dialog] [name=protein]').count()==0
                page.screenshot(path=str(output/'onboarding.png'),full_page=True)
                page.get_by_label('Name',exact=True).fill('Alex')
                page.get_by_label('Age',exact=True).fill('22')
                page.get_by_label('Height',exact=True).fill('173')
                page.get_by_label('Sex · BMR formula',exact=True).select_option('male')
                page.get_by_role('button',name='Continue',exact=True).click()
                page.get_by_role('heading',name='Starting point',exact=True).wait_for()
                assert page.locator('[name=calorie_target]').count()==0
                page.get_by_label('Today’s weight',exact=True).fill('80')
                page.get_by_label('Goal weight · optional',exact=True).fill('75')
                assert page.locator('[name=fat_free_mass],[name=body_fat_percent]').count()==0
                page.get_by_role('button',name='Done',exact=True).click()
                try:
                    page.wait_for_selector('[role=dialog]',state='detached',timeout=5000)
                except Exception:
                    page.screenshot(path=str(output/'setup-error.png'),full_page=True)
                    print(json.dumps({'browser_errors':errors,'fields':page.locator('[role=dialog] input').evaluate_all('(elements)=>elements.map(e=>({name:e.name,value:e.value,valid:e.validity.valid,message:e.validationMessage}))')},ensure_ascii=True),flush=True)
                    raise
                saved()
                assert store.settings()['onboarding_done']
                assert store.entries()[0]['weight']==80
                assert page.evaluate('state.today_stats.bmr')==1776.25
                assert 'Mifflin–St Jeor' in page.locator('#overview-readouts').inner_text()
                page.get_by_role('link',name='Settings',exact=True).click()
                assert page.locator('[name=fat_free_mass],[name=body_fat_percent]').count()==0
                page.screenshot(path=str(output/'mifflin-settings.png'))
                page.get_by_role('button',name='Formulas',exact=True).click()
                assert '10 × kg + 6.25 × cm' in page.locator('[role=dialog]').inner_text()
                assert '370 + 21.6' not in page.locator('[role=dialog]').inner_text()
                page.screenshot(path=str(output/'mifflin-formulas.png'))
                page.get_by_role('button',name='Close',exact=True).click()
                page.get_by_role('link',name='Overview',exact=True).click()
                assert page.get_by_role('button',name='Save',exact=False).count()==0
                assert page.locator('.sidebar-user,.sidebar-note,.hero').count()==0
                assert page.locator('input[name=calories]').count()==0
                assert page.locator('input[name=training_met]').count()==0
                assert page.locator('textarea').count()==0
                page.locator('#latest-weight-input').fill('79.8')
                assert page.locator('#latest-weight-input').evaluate('(element)=>element===document.activeElement')
                page.get_by_role('link',name='Insights',exact=True).click()
                assert '79.8 kg' in page.locator('#insight-plot title').text_content()
                page.get_by_role('link',name='Overview',exact=True).click()
                page.locator('#latest-weight-input').fill('80')
                saved()
                page.screenshot(path=str(output/'empty-overview.png'),full_page=True)
                # Each macro contributes immediately, independently of the other two.
                for macro,value,calories,tef in [('protein','150',600,150),('carbs','200',800,60),('fat','60',540,10.8)]:
                    page.locator(f'#today-{macro}').fill(value)
                    assert page.evaluate('state.today_stats.calories')==calories
                    assert page.evaluate('state.today_stats.tef')==tef
                    assert page.locator('#today-calories').get_attribute('placeholder')==str(calories)
                    saved()
                    assert store.entries()[0]['calories']==calories
                    assert store.state()['today_stats']['tef']==tef
                    assert all(store.entries()[0][key] is None for key in ('protein','carbs','fat') if key!=macro)
                    page.locator(f'#today-{macro}').fill('')
                    assert 'No data' in page.locator('#nutrition-totals').inner_text()
                    saved()
                    assert store.state()['summary']['total_deficit'] is None
                page.locator('#today-protein').fill('150')
                assert page.evaluate('state.today_stats.calories')==600
                page.locator('#today-fat').fill('60')
                assert page.evaluate('state.today_stats.calories')==1140
                page.locator('#today-carbs').fill('200')
                # Readouts and charts change before persistence is awaited.
                assert page.locator('#today-calories').get_attribute('placeholder')=='1,940'
                assert '220.8' in page.locator('#nutrition-totals').inner_text()
                assert '57' in page.locator('#overview-metrics').inner_text()
                saved()
                assert store.state()['today_stats']['deficit']==57.05
                assert page.locator('#today-carbs').input_value()=='200'
                assert page.locator('#today-training').is_visible()
                page.locator('#today-training').fill('40')
                saved()
                assert store.state()['today_stats']['deficit']==127.05
                page.get_by_label('Walking energy',exact=True).fill('100')
                saved()
                assert store.state()['today_stats']['deficit']==227.05
                # Change each required profile input and verify the live result.
                page.get_by_role('link',name='Settings',exact=True).click()
                sex=page.get_by_label('Sex · BMR formula',exact=True)
                sex.select_option('female')
                assert page.evaluate('state.today_stats.bmr')==1610.25
                saved()
                assert store.state()['today_stats']['bmr']==1610.25
                sex.select_option('')
                assert page.evaluate('state.today_stats.bmr') is None
                assert page.evaluate('state.today_stats.deficit') is None
                assert page.evaluate('state.today_stats.training_kcal')==70
                saved()
                assert store.settings()['sex'] is None
                sex.select_option('male')
                for label,changed,restored,expected in [('Height','174','173',1782.5),('Age','23','22',1771.25)]:
                    control=page.get_by_label(label,exact=True)
                    control.fill(changed)
                    assert page.evaluate('state.today_stats.bmr')==expected
                    saved()
                    assert store.state()['today_stats']['bmr']==expected
                    control.fill('')
                    assert page.evaluate('state.today_stats.bmr') is None
                    saved()
                    assert store.state()['today_stats']['tdee'] is None
                    control.fill(restored)
                    saved()
                page.get_by_role('link',name='Overview',exact=True).click()
                page.locator('#latest-weight-input').fill('81')
                assert page.evaluate('state.today_stats.bmr')==1786.25
                assert page.evaluate('state.today_stats.training_kcal')==70.875
                saved()
                page.locator('#latest-weight-input').fill('80')
                page.locator('#today-steps').fill('12000')
                assert page.evaluate('state.today_stats.tdee')==2167.05
                saved()
                page.locator('#today-steps').fill('')
                saved()
                # Simulate a slow local response while changing the same field again.
                def delayed(route):
                    time.sleep(.15)
                    route.continue_()
                page.route('**/api/entry',delayed)
                page.locator('#today-protein').fill('155')
                page.evaluate('() => { flushAll(); setTimeout(() => { const e=document.querySelector("#today-protein"); e.value="170"; e.dispatchEvent(new Event("input",{bubbles:true})); }, 20); }')
                page.wait_for_timeout(500)
                saved()
                page.unroute('**/api/entry',delayed)
                assert store.entries()[0]['protein']==170
                assert page.locator('#today-protein').input_value()=='170'
                assert store.entries()[0]['steps_kcal']==100
                # A delayed refresh cannot replace the result of a newer write.
                snapshot=page.request.get(url+'/api/state').json()
                def stale_refresh(route):
                    time.sleep(.35)
                    route.fulfill(status=200,content_type='application/json',body=json.dumps(snapshot))
                page.route('**/api/state',stale_refresh)
                page.evaluate('() => { refreshDay(); setTimeout(() => {const e=document.querySelector("#today-protein");e.value="180";e.dispatchEvent(new Event("input",{bubbles:true}));flushAll();},20); }')
                page.wait_for_timeout(600)
                page.unroute('**/api/state',stale_refresh)
                saved()
                assert store.entries()[0]['protein']==180
                assert page.locator('#today-calories').get_attribute('placeholder')=='2,060'
                page.locator('#today-protein').fill('170')
                saved()
                # Clearing one field must remove its entire derived contribution.
                page.locator('#today-carbs').fill('')
                assert page.locator('#today-calories').get_attribute('placeholder')=='1,220'
                assert '180.8' in page.locator('#nutrition-totals').inner_text()
                saved()
                assert store.state()['today_stats']['calories']==1220
                assert store.state()['summary']['total_deficit']==907.05
                page.locator('#today-carbs').fill('200')
                saved()
                page.get_by_role('link',name='Daily journal',exact=True).click()
                assert page.locator('#journal-period option:checked').inner_text()=='Current period'
                page.get_by_role('button',name=f'Open {actual_today.isoformat()}',exact=True).click()
                assert '170'==page.locator('#day-protein').input_value()
                assert page.get_by_role('button',name='Save',exact=False).count()==0
                page.get_by_role('button',name='Close',exact=True).click()
                # A skipped day has no calories, no invented weight, and no balance.
                clock[0]=actual_today+timedelta(days=2)
                page.evaluate('() => refreshDay()')
                page.get_by_role('link',name='Overview',exact=True).click()
                assert page.locator('#latest-weight-input').input_value()==''
                assert page.locator('#latest-weight-input').get_attribute('placeholder')=='80.0'
                assert page.locator('#today-protein').input_value()==''
                assert store.state()['today_stats']['bmr']==1776.25
                assert store.state()['today_stats']['deficit'] is None
                assert store.state()['summary']['deficit_days']==1
                page.get_by_role('link',name='Daily journal',exact=True).click()
                missed=(actual_today+timedelta(days=1)).isoformat()
                page.get_by_role('button',name=f'Open {missed}',exact=True).click()
                assert page.locator('#day-protein').input_value()==''
                page.locator('#day-protein').fill('150')
                page.locator('#day-fat').fill('60')
                page.locator('#day-carbs').fill('200')
                assert 'Late entry' in page.locator('#day-status').inner_text()
                saved()
                late=next(row for row in store.entries() if row['date']==missed)
                assert late['entered_late']==1
                assert late['weight'] is None
                page.get_by_role('button',name='Close',exact=True).click()
                assert page.locator(f'[data-day-cell="{missed}"]').get_by_text('Late entry',exact=True).count()==1
                # An interrupted save retries, retaining the current draft.
                failed=[False]
                def fail_once(route):
                    if not failed[0]:
                        failed[0]=True
                        route.fulfill(status=503,content_type='application/json',body='{"error":"Temporary interruption"}')
                    else:route.continue_()
                page.route('**/api/entry',fail_once)
                page.get_by_role('link',name='Overview',exact=True).click()
                page.locator('#today-protein').fill('125')
                page.wait_for_selector('#sync-status[data-state=error]')
                assert page.locator('#today-protein').input_value()=='125'
                page.wait_for_selector('#sync-status[data-state=saved]',timeout=10000)
                page.unroute('**/api/entry',fail_once)
                assert store.entries()[-1]['protein']==125
                # Daily meals with weekly weights must not fabricate chart points.
                saved();store.clear_history()
                measured_dates=[]
                for i in range(22):
                    clock[0]=actual_today-timedelta(days=21-i)
                    weight={0:82,7:81.5,14:81.5}.get(i)
                    if weight is not None:measured_dates.append(clock[0].isoformat())
                    store.save_entry({'date':clock[0].isoformat(),'weight':weight,'protein':150,'fat':60,'carbs':200,'training_minutes':40 if i==21 else None})
                page.reload()
                page.get_by_role('heading',name='Overview',exact=True).wait_for()
                assert page.locator('#latest-weight-input').input_value()==''
                assert page.locator('#latest-weight-input').get_attribute('placeholder')=='81.5'
                assert page.evaluate('state.today_stats.effective_weight')==81.5
                assert page.evaluate('state.today_stats.bmr')==1791.25
                assert page.evaluate('state.summary.weight_count')==3
                assert page.locator('#weight-plot .chart-hit').evaluate_all('(nodes)=>nodes.map(n=>n.dataset.chartDate)')==measured_dates
                assert page.locator('#weight-plot [data-chart-tick]').evaluate_all('(nodes)=>nodes.map(n=>n.dataset.chartTick)')==measured_dates
                page.screenshot(path=str(output/'weekly-weights-overview.png'))
                page.get_by_role('link',name='Insights',exact=True).click()
                assert page.locator('#insight-plot .chart-dot').count()==3
                page.screenshot(path=str(output/'weekly-weights-insights.png'))
                page.get_by_role('button',name='7D',exact=True).click()
                assert page.locator('#insight-plot .chart-dot').count()==0
                assert 'No measurements' in page.locator('#insight-plot').inner_text()
                page.get_by_role('link',name='Overview',exact=True).click()
                page.locator('#latest-weight-input').fill('81.4')
                assert page.locator('#weight-plot .chart-dot').count()==1
                assert page.locator('#weight-plot [data-chart-tick]').get_attribute('data-chart-tick')==actual_today.isoformat()
                assert float(page.locator('#weight-plot .chart-dot').get_attribute('cx'))==468.5
                saved()
                page.screenshot(path=str(output/'weekly-weights-single.png'))
                page.locator('#latest-weight-input').fill('')
                assert page.locator('#weight-plot .chart-dot').count()==0
                saved()
                page.get_by_role('button',name='30D',exact=True).click()
                assert page.locator('#weight-plot .chart-dot').count()==3
                assert store.entries()[-1]['weight'] is None
                page.reload()
                page.get_by_role('heading',name='Overview',exact=True).wait_for()
                assert page.locator('#weight-plot .chart-dot').count()==3
                # Replace only this temporary test database with chart fixtures.
                saved();store.clear_history();random.seed(12)
                for i in range(35):
                    clock[0]=actual_today-timedelta(days=34-i)
                    if i in (9,17,26):continue
                    store.save_entry({'date':clock[0].isoformat(),'weight':round(82.3-i*.065+random.uniform(-.2,.2),1),
                                      'protein':random.randint(130,170),'fat':random.randint(45,75),'carbs':random.randint(140,230),
                                      'training_minutes':40 if i%3==0 else None,'steps_kcal':random.randint(90,160)})
                clock[0]=actual_today
                store.save_entry({'date':(actual_today-timedelta(days=8)).isoformat(),'protein':150,'fat':60,'carbs':190})
                page.reload()
                page.get_by_role('heading',name='Overview',exact=True).wait_for()
                page.screenshot(path=str(output/'overview.png'),full_page=True)
                page.get_by_role('link',name='Insights',exact=True).click()
                assert page.locator('svg[role=img]').count()==1
                page.get_by_role('tab',name='Calories',exact=True).click()
                assert page.get_by_role('img',name='Calculated calorie history',exact=True).count()==1
                page.get_by_role('tab',name='Weight',exact=True).click()
                page.locator('[data-chart-kind=weight]').first.hover()
                assert page.locator('#chart-tooltip').is_visible()
                page.screenshot(path=str(output/'insights.png'),full_page=True)
                page.get_by_role('link',name='Daily journal',exact=True).click()
                page.screenshot(path=str(output/'history.png'),full_page=True)
                with page.expect_download() as downloaded:
                    page.get_by_role('button',name='CSV',exact=True).click()
                downloaded.value.save_as(str(output/'verified-export.csv'))
                assert 'Late entry' in (output/'verified-export.csv').read_text(encoding='utf-8-sig')
                page.get_by_role('link',name='Overview',exact=True).click()
                page.locator('#today-training').fill('40')
                saved()
                day_weight=store.state()['today_stats']['effective_weight']
                page.get_by_role('link',name='Settings',exact=True).click()
                assert page.locator('[name=tef_mode],[name=protein],[name=calorie_target]').count()==0
                page.get_by_label('Default training intensity',exact=True).fill('3.5')
                assert abs(page.evaluate('state.today_stats.training_kcal')-round(40*(3.5-1)*3.5*day_weight/200,3))<.001
                saved()
                assert store.settings()['training_met']==3.5
                assert store.entries()[0]['training_met']==2.25
                page.screenshot(path=str(output/'settings.png'),full_page=True)
                page.get_by_role('link',name='Overview',exact=True).click()
                for width in (390,768,1024,1440):
                    page.set_viewport_size({'width':width,'height':1000})
                    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'),f'Horizontal overflow at {width}'
                    if width==390:page.screenshot(path=str(output/'mobile.png'),full_page=True)
                page.get_by_role('link',name='Daily journal',exact=True).click()
                page.set_viewport_size({'width':1200,'height':780})
                assert page.locator('.journal-row').count()==8
                first_date=page.locator('.journal-row').first.get_attribute('data-date')
                page.get_by_role('button',name='Older days',exact=True).click()
                assert page.locator('.journal-row').first.get_attribute('data-date')!=first_date
                page.get_by_role('button',name='Newer days',exact=True).click()
                assert page.locator('.journal-row').first.get_attribute('data-date')==first_date
                # Archiving freezes completed days, keeps today and resets totals.
                before=store.state()
                page.get_by_role('button',name='Archive period',exact=True).click()
                page.get_by_role('button',name='Cancel',exact=True).click()
                assert store.state()==before
                page.get_by_role('button',name='Archive period',exact=True).click()
                page.locator('#archive-name').fill('Cut · autumn')
                page.screenshot(path=str(output/'archive-confirm.png'))
                page.get_by_role('button',name='Archive & start new',exact=True).click()
                page.wait_for_selector('[role=dialog]',state='detached')
                assert len(store.entries())==1
                assert store.state()['summary']['total_deficit']==before['today_stats']['deficit']
                assert store.entries()[0]['date']==actual_today.isoformat()
                archive_id=store.state()['archives'][0]['id']
                frozen=store.archive(archive_id)
                page.locator('#journal-period').select_option(str(archive_id))
                page.wait_for_function('() => archiveView !== null')
                assert page.locator('.journal-row').count()==8
                assert 'Read-only archive' in page.locator('#journal-footer').inner_text()
                page.screenshot(path=str(output/'archived-period.png'))
                archived_day=frozen['entries'][-1]['date']
                page.get_by_role('button',name=f'Open {archived_day}',exact=True).click()
                assert page.locator('#day-weight').is_disabled()
                assert page.locator('#day-protein').is_disabled()
                assert page.get_by_role('button',name='Delete day',exact=True).count()==0
                page.screenshot(path=str(output/'archived-day.png'))
                page.get_by_role('button',name='Close',exact=True).click()
                with page.expect_download() as archived_csv:
                    page.get_by_role('button',name='CSV',exact=True).click()
                archived_csv.value.save_as(str(output/'archive-export.csv'))
                with (output/'archive-export.csv').open(encoding='utf-8-sig',newline='') as exported_csv:
                    exported_rows=list(csv.reader(exported_csv,delimiter=';'))
                assert all(row[0]<actual_today.isoformat() for row in exported_rows[1:])
                page.get_by_role('link',name='Settings',exact=True).click()
                page.get_by_label('Age',exact=True).fill('30')
                saved()
                assert store.archive(archive_id)==frozen
                page.get_by_role('link',name='Daily journal',exact=True).click()
                page.locator('#journal-period').select_option('current')
                page.wait_for_function('() => archiveView === null')
                assert page.locator('.journal-row').count()==1
                page.screenshot(path=str(output/'new-period.png'))
                page.get_by_role('link',name='Overview',exact=True).click()
                assert page.locator('#today-protein').input_value()==str(before['today_stats']['protein']).removesuffix('.0')
                assert page.locator('[data-chart-date]').count()==1
                page.reload()
                page.get_by_role('heading',name='Overview',exact=True).wait_for()
                page.get_by_role('link',name='Daily journal',exact=True).click()
                assert page.locator('#journal-period option').count()==2
                page.get_by_role('button',name='Clear history',exact=True).click()
                page.get_by_role('button',name='Cancel',exact=True).click()
                assert store.entries()
                page.get_by_role('button',name='Clear history',exact=True).click()
                page.locator('[role=dialog]').get_by_role('button',name='Clear history',exact=True).click()
                page.wait_for_selector('[role=dialog]',state='detached')
                assert store.entries()==[]
                assert store.state()['archives']==[]
                assert store.settings()['name']=='Alex'
                # The empty label must not cover an unfinished or invalid weight.
                page.get_by_role('link',name='Overview',exact=True).click()
                weight_input=page.locator('#latest-weight-input')
                empty_weight=page.locator('.weight-empty')
                assert empty_weight.is_visible()
                for partial in ('8','19.9','500.1'):
                    weight_input.fill(partial)
                    assert empty_weight.is_hidden(),partial
                    assert weight_input.get_attribute('aria-invalid')=='true'
                    page.evaluate('() => refreshDay()')
                    assert weight_input.input_value()==partial
                    assert empty_weight.is_hidden(),partial
                    assert store.entries()==[]
                    assert page.evaluate('state.today_stats.effective_weight') is None
                    assert page.locator('#weight-plot .chart-dot').count()==0
                page.screenshot(path=str(output/'weight-input-invalid.png'))
                weight_input.fill('')
                weight_input.press_sequentially('1e')
                assert weight_input.evaluate('(input)=>input.validity.badInput')
                assert empty_weight.is_hidden()
                weight_input.fill('')
                assert empty_weight.is_visible()
                weight_input.press_sequentially('8')
                assert empty_weight.is_hidden()
                page.screenshot(path=str(output/'weight-input-partial.png'))
                weight_input.press_sequentially('1')
                assert weight_input.input_value()=='81'
                assert empty_weight.is_hidden()
                assert weight_input.get_attribute('aria-invalid') is None
                assert page.evaluate('state.today_stats.effective_weight')==81
                saved()
                assert store.entries()[0]['weight']==81
                assert page.locator('#weight-plot .chart-dot').count()==1
                page.screenshot(path=str(output/'weight-input-complete.png'))
                weight_input.fill('')
                saved()
                assert empty_weight.is_visible()
                assert store.state()['summary']['latest_weight'] is None
                assert not errors,errors
                print(json.dumps({'result':'passed','browser_errors':errors,'screenshots':str(output),'checks':['minimal UI','autosave onboarding','independent macro totals and TEF','live formulas and charts','slow response/latest edit wins','blank fields','carried weight','weekly measurements only on chart','measurement-date labels','single-point chart','skipped days excluded','day details','late entry provenance','automatic retry','MET autosave','CSV export','paginated journal','archive/current isolation','frozen read-only archives','archive export','history deletion']}))
                browser.close()
        finally:
            server.shutdown();server.server_close()


if __name__=='__main__':main()
