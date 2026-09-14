import unittest
import app
from scoring import DEFAULT_WEIGHTS

class ScoreV2Tests(unittest.TestCase):
    def test_five_dimensions_exact_and_missing_followers(self):
        rows=[dict(id='a',title='a',likes=10,favorites=10,comments=10,followers=100,publish_time='2026-09-10'),
              dict(id='b',title='b',likes=20,favorites=40,comments=20,followers=100,publish_time='2026-09-10'),
              dict(id='c',title='c',likes=0,favorites=0,comments=0,followers=0,publish_time='2026-09-10')]
        p={'sheets':[{'name':'test','rows':rows}],'mapping':{k:k for k in app.FIELDS},'as_of':'2026-09-10'}
        r=app.analyze(p);n={n['id']:n for n in r['notes']}
        self.assertEqual(n['a']['score'],0);self.assertEqual(n['b']['score'],100)
        self.assertIsNone(n['c']['score']);self.assertEqual(n['c']['score_missing'],['engagement_rate'])
        self.assertEqual(n['c']['favorite_value'],0)
        self.assertEqual(r['weights'],{k:v/100 for k,v in DEFAULT_WEIGHTS.items()})
        self.assertAlmostEqual(n['a']['engagement_rate'],.3)
        self.assertAlmostEqual(n['b']['favorite_value'],40/21)
    def test_unmapped_dimension_is_explicitly_removed(self):
        p={'sheets':[{'name':'test','rows':[{'title':'a','likes':0},{'title':'b','likes':10}]}],'mapping':{'title':'title','likes':'likes'}}
        r=app.analyze(p);self.assertEqual(r['weights'],{'popularity':1})
        self.assertEqual([n['score'] for n in r['notes']],[100,0])

if __name__=='__main__':unittest.main()
