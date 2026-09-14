import unittest
import app
from content_generator import generate_plan, retrieve

class GeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data=app.read_file((app.ROOT/'小红书好物分享500参考笔记.xlsx').read_bytes(),'source.xlsx')
        data['as_of']='2026-09-10'
        cls.analysis=app.analyze(data)

    def test_plate_retrieval_evidence_and_drafts(self):
        plan=generate_plan(self.analysis,'手作餐盘','餐具爱好者')
        self.assertEqual(plan['category'],'创意餐盘')
        self.assertEqual(plan['status'],'ready')
        self.assertEqual(plan['matched_count'],242)
        self.assertEqual(len(plan['plans']),3)
        lookup={n['id']:n for n in self.analysis['notes']}
        for ref in plan['references']:
            self.assertTrue(lookup[ref['id']]['high'])
            self.assertIn('创意餐盘',lookup[ref['id']]['tags'])
        for row in plan['hooks']+plan['structures']+plan['scenes']:
            for evidence in row['examples']:
                n=lookup[evidence['id']]
                self.assertIn(evidence['quote'],n['title']+'\n'+n['content'])
        self.assertEqual(len(set(p['body'] for p in plan['plans'])),3)
        self.assertTrue(all('手作餐盘' in p['body'] for p in plan['plans']))

    def test_no_unrelated_fallback(self):
        p=generate_plan(self.analysis,'跑步鞋')
        self.assertEqual(p['status'],'insufficient')
        self.assertEqual(p['plans'],[])
        p=generate_plan(dict(self.analysis,notes=[n for n in self.analysis['notes'] if not n['high']]),'手作餐盘')
        self.assertEqual(p['references'],[])

    def test_explicit_category_precedes_mentions(self):
        notes=[{'id':'a','title':'餐盘配咖啡杯','tags':'杯碗茶具'}, {'id':'b','title':'手作餐盘','tags':''}]
        _,matched=retrieve(notes,'手作餐盘')
        self.assertEqual([n['id'] for n in matched],['b'])

    def test_title_only_and_low_sample(self):
        n=dict(self.analysis['notes'][0],content='',tags='创意餐盘',title='神仙餐盘',high=True)
        p=generate_plan(dict(self.analysis,notes=[n]),'手作餐盘')
        self.assertTrue(any('不足 5' in a for a in p['advice']))
        self.assertTrue(any('缺少正文' in a for a in p['advice']))
        self.assertTrue(all(row['count']==0 for row in p['structures']))

if __name__=='__main__': unittest.main()
