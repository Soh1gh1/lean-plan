"""Inspect fixed-canvas geometry and export review screenshots without real data."""
import argparse
from datetime import date, timedelta
import json
from pathlib import Path
import random
import tempfile
import threading

from playwright.sync_api import sync_playwright

from leanplan.desktop import fit_window_bounds
from leanplan.server import create_server
from leanplan.store import Store


ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',default='test-results/geometry/iteration-1')
    parser.add_argument('--matrix',action='store_true')
    args=parser.parse_args()
    output=ROOT/args.out
    output.mkdir(parents=True,exist_ok=True)
    today=date.today()
    clock=[today-timedelta(days=45)]
    with tempfile.TemporaryDirectory() as directory:
        store=Store(Path(directory),lambda:clock[0])
        store.save_settings({'name':'Alex','sex':'male','age':22,'height':173,'goal_weight':75,'onboarding_done':True})
        random.seed(12)
        for i in range(46):
            clock[0]=today-timedelta(days=45-i)
            if i in (10,22,38):continue
            store.save_entry({'date':clock[0].isoformat(),'weight':round(82.8-i*.055+random.uniform(-.15,.15),1),
                              'protein':random.randint(130,170),'fat':random.randint(45,75),'carbs':random.randint(140,230),
                              'training_minutes':40 if i%3==0 else None,'steps_kcal':100 if i%4==0 else None,
                              'note':'Morning measurement.' if i==45 else ''})
        clock[0]=today
        late=today-timedelta(days=8)
        store.save_entry({'date':late.isoformat(),'protein':150,'fat':60,'carbs':190})
        server=create_server(store,ROOT/'static')
        threading.Thread(target=server.serve_forever,daemon=True).start()
        url=f'http://127.0.0.1:{server.server_port}'
        results=[]
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
                cases=[('base',1200,780,1)]
                if args.matrix:
                    for label,w,h,dpi in [('small-100',1366,720,96),('small-125',1280,672,120),('fhd-125',1920,1040,120),('fhd-200',1920,1040,192),('qhd-150',2560,1392,144),('uhd-200',3840,2112,192),('ultrawide-125',3440,1392,120)]:
                        bounds=fit_window_bounds((0,0,w,h),dpi,round(2*dpi/96),round(31*dpi/96))
                        cases.append((label,round(bounds.client_width*96/dpi),round(bounds.client_height*96/dpi),dpi/96))
                cases.append(('empty',1200,780,1))
                for label,w,h,dpr in cases:
                    if label=='empty':store.clear_history()
                    context=browser.new_context(viewport={'width':w,'height':h},device_scale_factor=dpr,color_scheme='light')
                    page=context.new_page()
                    errors=[]
                    page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(url)
                    page.get_by_role('heading',name='Overview',exact=True).wait_for()
                    geometry={}
                    for name in ('overview','history','insights','settings'):
                        page.locator(f'nav a[data-page={name}]').click()
                        snap=page.evaluate('''() => {
                          const frame=document.querySelector('#app-frame').getBoundingClientRect(),scale=window.leanplanScale;
                          const rect=selector=>{const r=document.querySelector(selector)?.getBoundingClientRect();return r?{x:(r.x-frame.x)/scale,y:(r.y-frame.y)/scale,width:r.width/scale,height:r.height/scale}:null;};
                          const overflow=[...document.querySelectorAll('#app-frame *')].filter(e=>e.getClientRects().length&& !e.closest('svg') && !['INPUT','SELECT','TEXTAREA','OPTION'].includes(e.tagName) && e.clientHeight>0 && (e.scrollHeight>e.clientHeight+2||e.scrollWidth>e.clientWidth+2)).map(e=>({tag:e.tagName,id:e.id,className:e.className,client:[e.clientWidth,e.clientHeight],scroll:[e.scrollWidth,e.scrollHeight]}));
                          return {header:rect('.page-header'),body:rect('.page-body'),chart:rect('[data-layout=chart]'),frame:{x:frame.x,y:frame.y,right:frame.right,bottom:frame.bottom},scale,overflow,rootScroll:[document.documentElement.scrollWidth,document.documentElement.scrollHeight],view:[innerWidth,innerHeight]};
                        }''')
                        geometry[name]=snap
                        if label=='base':page.screenshot(path=str(output/f'{name}.png'),animations='disabled')
                        if snap['overflow']:
                            print(json.dumps({'page':name,'overflow':snap['overflow'],'metrics':page.locator('.metric').evaluate_all('(elements)=>elements.map(e=>({height:e.getBoundingClientRect().height,children:[...e.children].map(c=>({tag:c.tagName,h:c.getBoundingClientRect().height,text:c.textContent,style:getComputedStyle(c).lineHeight}))}))')},ensure_ascii=True),flush=True)
                        assert not snap['overflow'],(label,name,snap['overflow'])
                        assert snap['rootScroll'][0]<=w and snap['rootScroll'][1]<=h,(label,name,snap)
                        assert snap['frame']['x']>=-.5 and snap['frame']['y']>=-.5
                        assert snap['frame']['right']<=w+.5 and snap['frame']['bottom']<=h+.5
                        for key,expected in [('x',212),('y',88),('width',960),('height',664)]:
                            assert abs(snap['body'][key]-expected)<.1,(label,name,key,snap['body'])
                        for key in ('x','y','width','height'):
                            assert abs(snap['header'][key]-geometry['overview']['header'][key])<.1,(label,name,'header',snap)
                    for view in ('overview','insights'):
                        for key,expected in [('x',212),('y',484),('width',960),('height',268)]:
                            assert abs(geometry[view]['chart'][key]-expected)<.1,(label,view,'chart geometry',geometry[view]['chart'])
                    page.locator('nav a[data-page=history]').click()
                    assert 1<=page.locator('.journal-row').count()<=8
                    assert page.locator('.calendar-day,.skip-link').count()==0
                    page.get_by_role('button',name=f'Open {today.isoformat()}',exact=True).click()
                    for tab in ('Measurements','Activity'):
                        page.get_by_role('tab',name=tab,exact=True).click()
                        rect=page.locator('[role=dialog]').bounding_box()
                        assert rect['x']>=0 and rect['y']>=0 and rect['x']+rect['width']<=w+.5 and rect['y']+rect['height']<=h+.5,(label,tab,rect)
                        overflow=page.locator('[role=dialog]').evaluate('(e)=>({h:e.scrollHeight-e.clientHeight,w:e.scrollWidth-e.clientWidth})')
                        assert overflow['h']<=2 and overflow['w']<=2,(label,tab,overflow)
                        assert page.get_by_role('tab',name=tab,exact=True).get_attribute('aria-selected')=='true'
                        if label=='base':page.screenshot(path=str(output/f'day-{tab.lower()}.png'),animations='disabled')
                    page.get_by_role('button',name='Close',exact=True).click()
                    page.locator('nav a[data-page=settings]').click()
                    page.get_by_role('button',name='Formulas',exact=True).click()
                    if label=='base':page.screenshot(path=str(output/'formulas.png'))
                    page.get_by_role('button',name='Close',exact=True).click()
                    fullscreen=page.evaluate('() => document.documentElement.requestFullscreen().then(()=>true).catch(()=>false)')
                    assert fullscreen is False
                    page.mouse.wheel(0,2000)
                    assert page.evaluate('scrollY')==0
                    assert not errors,errors
                    results.append({'case':label,'viewport':[w,h],'dpr':dpr,'geometry':geometry})
                    if label!='base':
                        page.locator('nav a[data-page=overview]').click()
                        page.screenshot(path=str(output/f'{label}.png'))
                    context.close()
                browser.close()
        finally:
            server.shutdown();server.server_close()
    (output/'geometry.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps({'result':'passed','cases':len(results),'screenshots':str(output),'checks':['identical page bounds','identical header coordinates','full-width chart coordinates','paginated journal list','fixed day dialog','no overflow','no page scrolling','fullscreen denied']}))


if __name__=='__main__':main()
