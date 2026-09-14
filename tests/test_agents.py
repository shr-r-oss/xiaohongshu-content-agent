import copy
import json
import unittest
import io
from unittest.mock import patch
import app
from scoring import association
from agent_pipeline import semantic_batch,summarize_semantics,SEMANTIC_FEATURES,review,optimize,evaluate_all,validate_plans

def encoded(value): return {'text':json.dumps(value,ensure_ascii=False)}

class AgentsTests(unittest.TestCase):
    def setUp(self):
        self.context={'topic':'小熊餐盘','brief':'自然表达','facts':'用户提供：小熊造型','references':[{'id':'ref','content':'参考文字'}]}
        self.plan={'angle':'测试','topic':'小熊餐盘','titles':['小熊餐盘怎么选','小熊餐盘的细节','小熊餐盘搭配'],
                   'body':'小熊餐盘的选择\n\n【待补充尺寸】\n\n根据自己的需要选择。','tags':[],'outline':[],'visuals':[],'reference_ids':['ref']}
    def test_lift_and_missing_baseline(self):
        r=association(60,100,40,400)
        self.assertAlmostEqual(r['lift'],3)
        self.assertEqual(r['association'],'正关联')
        self.assertEqual(association(10,100,100,400)['association'],'负关联')
        self.assertIsNone(association(0,100,0,400)['lift'])
        self.assertIsNone(association(1,1,0,0)['lift'])
    def test_semantic_blind_and_evidence_validation(self):
        notes=[{'id':'1','title':'餐盘','content':'选择适合自己的尺寸','high':True,'score':99}]
        def mock(payload):
            self.assertNotIn('high',payload['structured_data']['notes'][0])
            self.assertNotIn('score',payload['structured_data']['notes'][0])
            return encoded({'notes':[{'id':'1','features':{k:{'present':True,'quote':'适合自己的尺寸','reason':'帮助选择'} for k in SEMANTIC_FEATURES}}]})
        result=semantic_batch(notes,mock)
        self.assertEqual(len(result['notes']),1)
        def bad(payload):
            r=mock(payload);v=json.loads(r['text']);v['notes'][0]['features']['情绪共鸣']['quote']='不存在的原文';return encoded(v)
        with self.assertRaisesRegex(ValueError,'无法在原文定位'): semantic_batch(notes,bad)
    def test_semantic_unknown_not_negative(self):
        notes=[{'id':'1','high':True},{'id':'2','high':False}]
        annotations=[{'id':'1','features':{k:{'present':None} for k in SEMANTIC_FEATURES}}, {'id':'2','features':{k:{'present':False} for k in SEMANTIC_FEATURES}}]
        rows=summarize_semantics(notes,annotations)
        self.assertEqual(rows[0]['total'],0)
        self.assertIsNone(rows[0]['lift'])
    def test_review_preserves_factual_blockers_and_rejects_bounds(self):
        def response(payload): return encoded({'dimensions':{'需求匹配':20,'标题吸引力':20,'事实完整度':20,'结构清晰度':15,'原创度':15,'参考过度相似风险':10},'issues':[],'blockers':[],'rationale':'测试'})
        r=review(self.plan,self.context,response)
        self.assertIn('仍含待补充事实',r['blockers'])
        def invalid(payload):
            r=json.loads(response(payload)['text']);r['dimensions']['事实完整度']=100;return encoded(r)
        with self.assertRaisesRegex(ValueError,'超出量表'): review(self.plan,self.context,invalid)
    def test_local_optimization_does_not_invent_facts(self):
        p=copy.deepcopy(self.plan);p['body']+='闭眼入'
        r=optimize(p,self.context)
        self.assertTrue(r['accepted'])
        self.assertIn('【待补充尺寸】',r['final']['body'])
        self.assertNotIn('闭眼入',r['final']['body'])
        self.assertEqual(p['body'],self.plan['body']+'闭眼入')
    def test_optimization_rolls_back_if_score_drops(self):
        reviews=0
        def model(payload):
            nonlocal reviews
            if payload['task']=='optimize':
                p=copy.deepcopy(self.plan);p['body']+='\n优化后的句子';return encoded({'plan':p,'changes':['增加一句']})
            reviews+=1
            return encoded({'dimensions':{'需求匹配':20 if reviews==1 else 0,'标题吸引力':10,'事实完整度':10,'结构清晰度':10,'原创度':10,'参考过度相似风险':10},'issues':[],'blockers':[],'rationale':'测试复评'})
        r=optimize(self.plan,self.context,model)
        self.assertFalse(r['accepted']);self.assertEqual(r['final'],self.plan)
    def test_three_plans_and_reference_validation(self):
        with self.assertRaises(ValueError): validate_plans([self.plan],['ref'])
        ps=[copy.deepcopy(self.plan) for _ in range(3)];ps[1]['reference_ids']=['unknown']
        with self.assertRaisesRegex(ValueError,'未检索'): validate_plans(ps,['ref'])
        result=evaluate_all([self.plan]*3,self.context)
        self.assertEqual(result['best_index'],0)

    def test_structured_model_transport(self):
        app.AI_CACHE.clear()
        config={'AI_BASE_URL':'https://model.example/v1','AI_API_KEY':'test-only','AI_MODEL':'mock-json'}
        def provider(request,timeout):
            data=json.loads(request.data)
            self.assertIn('JSON',data['messages'][0]['content'])
            user=json.loads(data['messages'][1]['content'])
            self.assertEqual(user['task'],'intent')
            self.assertEqual(user['data']['topic'],'小熊餐盘')
            return io.BytesIO(json.dumps({'choices':[{'message':{'content':'{"category":"创意餐盘"}'}}]}).encode())
        with patch.object(app,'load_config',return_value=config),patch.object(app.urllib.request,'urlopen',side_effect=provider):
            r=app.run_ai({'task':'intent','structured_data':{'topic':'小熊餐盘'},'schema_instruction':'返回 JSON'})
        self.assertEqual(json.loads(r['text'])['category'],'创意餐盘')

if __name__=='__main__':unittest.main()
