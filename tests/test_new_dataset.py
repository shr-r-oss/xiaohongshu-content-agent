import unittest
import app
from content_generator import generate_plan,retrieve
from dataset_diagnostics import distribution_report
from agent_pipeline import evaluate_all,optimize

class NewDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        file=app.ROOT/'小红书好物分享500模拟数据.csv'
        cls.data=app.read_file(file.read_bytes(),file.name)
        cls.data['as_of']='2026-09-10';cls.result=app.analyze(cls.data)
    def test_import_distribution(self):
        self.assertTrue(self.data['simulated'])
        self.assertEqual(self.result['total'],500)
        self.assertEqual(self.result['scored'],500)
        self.assertEqual(self.result['medians']['likes'],1287.5)
        self.assertEqual(self.result['high_count'],100)
        self.assertEqual(self.result['issues'],[])
    def test_new_categories(self):
        category,notes=retrieve(self.result['notes'],'托盘')
        self.assertEqual(category,'托盘与收纳');self.assertEqual(len(notes),61)
        _,notes=retrieve(self.result['notes'],'厨房小物');self.assertEqual(len(notes),39)
        scoped=app.analyze({**self.data,'filters':{'category':'创意餐盘'}})
        self.assertEqual(len(scoped['notes']),198)
        self.assertEqual(scoped['high_count'],40)
    def test_bear_evidence_and_strategy(self):
        g=generate_plan(self.result,'小熊餐盘')
        self.assertEqual(g['matched_count'],198)
        self.assertGreater(g['similar_high_count'],0)
        self.assertIn('小熊',g['references'][0]['title']+g['references'][0]['content'])
        for p in g['plans']:
            self.assertEqual(len(p['titles']),3)
            self.assertTrue(p['strategy']['objective'])
            self.assertTrue(p['strategy']['evidence'])
        self.assertTrue(all(n['match_reasons'] for n in g['references']))
        assessment=evaluate_all(g['plans'],g)
        self.assertGreater(len(set(e['score'] for e in assessment['evaluations'])),1)
        self.assertIn('胜出',assessment['winner_reason'])
    def test_score_sensitivity(self):
        report=distribution_report(self.result,self.data['mapping'])
        self.assertEqual(len(report['sensitivity']),5)
        self.assertEqual(report['distribution']['likes']['median'],1287.5)
        for s in report['sensitivity']:self.assertTrue(0<=s['retention_pct']<=100)
        self.assertNotIn('accuracy',report)

if __name__=='__main__':unittest.main()
