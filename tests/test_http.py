import csv
from datetime import date, timedelta
from io import StringIO
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from leanplan.server import create_server
from leanplan.store import Store


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.today = date(2026,11,9)
        self.store = Store(Path(self.temp.name),lambda:self.today)
        self.server = create_server(self.store,Path(__file__).resolve().parents[1]/'static')
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        with urlopen(self.url+'/api/state') as response:
            self.token = json.load(response)['token']

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.temp.cleanup()

    def post(self,path,data,headers=None):
        return urlopen(Request(self.url+path,json.dumps(data).encode(),headers=headers or {'X-Leanplan-Token':self.token,'Content-Type':'application/json'}))

    def assert_rejected(self,path,data,status):
        with self.assertRaises(HTTPError) as error:
            self.post(path,data)
        self.assertEqual(error.exception.code,status)
        error.exception.close()

    def test_today_macros_calculate_calories_and_export_without_injection(self):
        with self.post('/api/entry',{'date':self.today.isoformat(),'weight':80,'protein':150,'fat':60,'carbs':200,'note':'=SUM(1;2)'}) as response:
            self.assertEqual(json.load(response)['entries'][0]['calories'],1940)
        with urlopen(self.url+'/api/export/csv') as response:
            rows = list(csv.reader(StringIO(response.read().decode('utf-8-sig')),delimiter=';'))
        self.assertIn('Calculated calories, kcal',rows[0])
        self.assertIn('Protein, g',rows[0])
        self.assertTrue(rows[1][-1].startswith("'="))

    def test_backfill_is_marked_late_and_manual_calories_are_rejected(self):
        today=self.today.isoformat()
        with self.post('/api/entry',{'date':today,'weight':80}) as response:
            response.read()
        self.today += timedelta(days=1)
        with self.post('/api/entry',{'date':today,'weight':79}) as response:
            self.assertEqual(json.load(response)['entries'][0]['entered_late'],1)
        with self.post('/api/entry',{'date':(self.today-timedelta(days=5)).isoformat(),'weight':78}) as response:
            self.assertEqual(json.load(response)['entries'][0]['entered_late'],1)
        self.assert_rejected('/api/entry',{'date':self.today.isoformat(),'calories':2000},400)
        self.assert_rejected('/api/restore',{'format':'leanplan','version':1,'entries':[]},404)
        self.assertEqual(self.store.entries()[-1]['weight'],79)

    def test_delete_specific_past_day_and_clear_all_require_explicit_action(self):
        yesterday=self.today.isoformat()
        with self.post('/api/entry',{'date':yesterday,'weight':80}) as response:response.read()
        self.today += timedelta(days=1)
        with self.post('/api/entry',{'date':self.today.isoformat(),'weight':79}) as response:response.read()
        with self.post('/api/delete',{'date':yesterday}) as response:
            self.assertEqual(len(json.load(response)['entries']),1)
        self.assert_rejected('/api/history/clear',{},400)
        self.assertEqual(len(self.store.entries()),1)
        with self.post('/api/history/clear',{'confirmation':'CLEAR'}) as response:
            self.assertEqual(json.load(response)['entries'],[])

    def test_tokens_cross_origin_and_private_routes_are_protected(self):
        for headers in ({'Content-Type':'application/json'},{'X-Leanplan-Token':self.token,'Origin':'https://other.example'}):
            with self.assertRaises(HTTPError) as error:
                self.post('/api/entry',{'date':self.today.isoformat(),'weight':80},headers)
            self.assertEqual(error.exception.code,403)
            error.exception.close()
        for path in ('/data/leanplan.sqlite3','/app.py','/../app.py'):
            with self.assertRaises(HTTPError) as error:urlopen(self.url+path)
            self.assertEqual(error.exception.code,404)
            error.exception.close()

    def test_archive_routes_preserve_today_and_export_the_selected_period(self):
        yesterday=(self.today-timedelta(days=1)).isoformat()
        macros={'protein':150,'fat':60,'carbs':200}
        self.store.save_entry({'date':yesterday,'weight':80,**macros})
        self.store.save_entry({'date':self.today.isoformat(),**macros})
        self.assert_rejected('/api/period/archive',{'name':''},400)
        with self.post('/api/period/archive',{'name':'Cut'}) as response:
            current=json.load(response)
        self.assertEqual(len(current['entries']),1)
        self.assertEqual(current['entries'][0]['date'],self.today.isoformat())
        archive_id=current['archives'][0]['id']
        with urlopen(self.url+f'/api/archives/{archive_id}') as response:
            archive=json.load(response)
        self.assertEqual(archive['entries'][0]['date'],yesterday)
        self.assertTrue(archive['read_only'])
        with urlopen(self.url+f'/api/export/csv?archive={archive_id}') as response:
            rows=list(csv.reader(StringIO(response.read().decode('utf-8-sig')),delimiter=';'))
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[1][0],yesterday)
        with urlopen(self.url+'/api/export/json') as response:
            exported=json.load(response)
        self.assertEqual(len(exported['archives']),1)
        self.assert_rejected('/api/entry',{'date':yesterday,'weight':75},400)
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url+'/api/archives/9999')
        self.assertEqual(error.exception.code,404)
        error.exception.close()


if __name__=='__main__':unittest.main()
