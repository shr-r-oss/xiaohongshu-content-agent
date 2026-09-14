import unittest
import copy
import app
from screenshot_notes import score_external, recognize_image, appreciate

class ScreenshotTests(unittest.TestCase):
    def setUp(self):
        rows=[dict(title=str(i),likes=i*100,favorites=i*40,comments=i*5,followers=1000,publish_time='2026-09-01') for i in range(1,6)]
        self.reference=app.analyze({'sheets':[{'name':'test','rows':rows}],'mapping':{k:k for k in app.FIELDS},'as_of':'2026-09-10'})
        self.fields=dict(title='杯子',likes=300,favorites=120,comments=15)

    def test_partial_and_fixed_reference(self):
        original=copy.deepcopy(self.reference)
        out=score_external(self.fields,self.reference,app.number)
        self.assertEqual(out['status'],'部分维度参考分')
        self.assertEqual(set(out['missing']),{'velocity','engagement_rate'})
        self.assertAlmostEqual(out['score'],50)
        self.assertEqual(self.reference,original)

    def test_complete_and_invalid_date(self):
        fields={**self.fields,'followers':1000,'publish_time':'2026-09-01'}
        out=score_external(fields,self.reference,app.number)
        self.assertEqual(out['status'],'完整 ViralScore')
        self.assertAlmostEqual(out['score'],50)
        for date in ['05-03','2027-01-01']:
            with self.assertRaises(ValueError):score_external({**fields,'publish_time':date},self.reference,app.number)

    def test_zero_is_observed_and_blank_missing(self):
        out=score_external(dict(title='a',likes=0,favorites=0,comments=0,followers=0),self.reference,app.number)
        self.assertEqual(out['score'],0)
        self.assertIn('engagement_rate',out['missing'])
        self.assertIsNone(score_external({'title':'a'},self.reference,app.number)['score'])
        with self.assertRaises(ValueError):score_external({**self.fields,'likes':-1},self.reference,app.number)

    def test_invalid_image(self):
        with self.assertRaises(ValueError):recognize_image(b'not an image')

    def test_content_appreciation_needs_no_metrics(self):
        out=appreciate({'title':'Mark 适合送朋友的实用杯子','content':'你们更喜欢哪一个？','tags':'#杯子推荐','cover_text':'蓝绿色流釉，像梦幻油画'})
        self.assertEqual(len(out['items']),6)
        self.assertGreater(out['score'],0)
        self.assertEqual({x['key'] for x in out['items']},{'title_attraction','favorite_intent','visual_expression','scene','selling_points','interaction'})

if __name__=='__main__':unittest.main()
