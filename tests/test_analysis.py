import csv
import io
import unittest
from unittest.mock import patch
import app

class AnalysisTests(unittest.TestCase):
    def payload(self, rows, **kwargs):
        return dict(sheets=[{'name':'test','rows':rows}],mapping={k:k for k in app.FIELDS if k not in ['publish_time','followers']},**kwargs)

    def test_source(self):
        d=app.read_file((app.ROOT/'小红书好物分享500参考笔记.xlsx').read_bytes(),'source.xlsx')
        r=app.analyze(d)
        self.assertTrue(d['simulated'])
        self.assertEqual([len(s['rows']) for s in d['sheets']],[250,250])
        self.assertEqual((r['total'],r['scored'],r['high_count']),(500,500,100))
        self.assertEqual(r['issues'],[])
        # Verify against independently sorted source values, not the scoring implementation.
        top=r['notes'][0]
        raw=[row for s in d['sheets'] for row in s['rows']]
        import statistics
        expected=sum(w*(sum(n[k]<top[k] for n in r['notes'])+(sum(n[k]==top[k] for n in r['notes'])-1)/2)/499*100 for k,w in [('popularity',.25),('engagement_rate',.25),('favorite_value',.25),('velocity',.15),('comment',.10)])
        self.assertAlmostEqual(top['score'],expected)

    def test_ties_missing_single(self):
        rows=[dict(id=str(i),title=f'n{i}',likes=10,favorites=10,comments=10) for i in range(3)]
        r=app.analyze(self.payload(rows))
        self.assertEqual([n['score'] for n in r['notes']],[50,50,50])
        rows[1]['likes']=None
        r=app.analyze(self.payload(rows))
        self.assertEqual(r['scored'],2)
        self.assertIsNone(next(n for n in r['notes'] if n['id']=='1')['score'])
        self.assertIsNone(app.analyze(self.payload(rows[:1]))['notes'][0]['score'])

    def test_units_duplicates_and_zero(self):
        self.assertEqual(app.number('1.2万'),12000)
        self.assertEqual(app.number('3k'),3000)
        self.assertEqual(app.number('0'),0)
        self.assertIsNone(app.number('-1'))
        self.assertIsNone(app.number('NaN'))
        rows=[dict(id='a',title='a',likes=0,favorites=0,comments=0)]*2+[dict(title='')]
        r=app.analyze(self.payload(rows))
        self.assertEqual(r['total'],1)
        self.assertEqual(len(r['issues']),2)

    def test_weight_change_and_source_label_independence(self):
        rows=[dict(id='a',title='a',likes=100,favorites=0,comments=0),dict(id='b',title='b',likes=0,favorites=100,comments=0)]
        a=app.analyze(self.payload(rows,weights={'popularity':1}))
        b=app.analyze(self.payload(rows,weights={'favorite_value':1}))
        self.assertEqual(a['notes'][0]['id'],'a')
        self.assertEqual(b['notes'][0]['id'],'b')
        p=self.payload(rows,weights={'popularity':1,'favorite_value':1}); p['sheets'][0]['name']='爆款笔记'
        self.assertEqual(app.analyze(p)['notes'][0]['score'],50)

    def test_csv_multiline_and_html(self):
        data='标题,正文,点赞数\r\n"标题,<script>","第一行\n第二行",1.2万\r\n'
        d=app.read_file(data.encode('utf-8-sig'),'a.csv')
        self.assertEqual(d['sheets'][0]['rows'][0]['正文'],'第一行\n第二行')
        self.assertEqual(d['mapping']['likes'],'点赞数')
        self.assertEqual(app.analyze(d)['notes'][0]['likes'],12000)

    def test_filters(self):
        rows=[dict(id='a',title='cup',likes=1,publish_time='2026-01-01'),dict(id='b',title='plate',likes=2,publish_time='bad')]
        p=self.payload(rows,weights={'popularity':1},filters={'start':'2026-01-01'});p['mapping']['publish_time']='publish_time'
        r=app.analyze(p)
        self.assertEqual([n['id'] for n in r['notes']],['a'])

    def test_ai_contract_and_cache(self):
        import json
        app.AI_CACHE.clear()
        config={'AI_BASE_URL':'https://model.example/v1','AI_API_KEY':'test-key','AI_MODEL':'test-model'}
        sent=[]
        def reply(request,timeout):
            sent.append(json.loads(request.data))
            self.assertEqual(request.full_url,'https://model.example/v1/chat/completions')
            return io.BytesIO(json.dumps({'choices':[{'message':{'content':'测试输出，非真实模型结果'}}]}).encode())
        payload={'task':'breakdown','simulated':True,'notes':[{'id':'a','title':'title','content':'正文','author':'private author','score':90,'high':True}]}
        with patch.object(app,'load_config',return_value=config), patch.object(app.urllib.request,'urlopen',side_effect=reply):
            self.assertFalse(app.run_ai(payload)['cached'])
            self.assertTrue(app.run_ai(payload)['cached'])
        self.assertEqual(len(sent),1)
        self.assertNotIn('private author',json.dumps(sent))
        self.assertTrue(json.loads(sent[0]['messages'][1]['content'])['simulated'])
        with patch.object(app,'load_config',return_value={k:'' for k in config}):
            with self.assertRaisesRegex(ValueError,'尚未连接'): app.run_ai(payload)

    def test_velocity_and_followers(self):
        rows=[dict(id=str(i),title=str(i),likes=10,favorites=5,comments=5,followers=f,publish_time=d) for i,(d,f) in enumerate([('2026-09-10',10),('2026-09-09',0),('2026-09-11',None)])]
        p=self.payload(rows,as_of='2026-09-10',top_pct=50,weights={'velocity':1});p['mapping']['followers']='followers'
        p['mapping']['publish_time']='publish_time'
        r=app.analyze(p); by_id={n['id']:n for n in r['notes']}
        self.assertEqual(by_id['0']['velocity'],20)
        self.assertEqual(by_id['1']['velocity'],10)
        self.assertEqual(by_id['0']['engagement_rate'],2)
        self.assertIsNone(by_id['1']['engagement_rate'])
        self.assertIsNone(by_id['2']['score'])
        self.assertAlmostEqual(by_id['0']['score'],100)
        self.assertAlmostEqual(by_id['1']['score'],0)
        self.assertEqual(r['high_count'],1)

if __name__=='__main__': unittest.main()
