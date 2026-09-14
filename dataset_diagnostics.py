"""Descriptive score checks, never substitutes synthetic tiers for ground truth."""
import copy
import math
import statistics
from scoring import score_notes

def distribution_report(analysis,mapping):
    notes=analysis['notes'];valid=[n for n in notes if n['score'] is not None]
    def quantiles(values):
        values=sorted(values)
        def q(p):
            if not values:return None
            x=(len(values)-1)*p;i=math.floor(x);return values[i]+(values[min(i+1,len(values)-1)]-values[i])*(x-i)
        return dict(p10=q(.1),median=q(.5),p90=q(.9),p99=q(.99),maximum=max(values) if values else None)
    baseline={n['id'] for n in valid if n['high']};sensitivity=[]
    for excluded in analysis['weights']:
        weights={k:v for k,v in analysis['weights'].items() if k!=excluded}
        if not weights:continue
        sample=copy.deepcopy(valid);score_notes(sample,mapping,weights)
        sample=sorted(sample,key=lambda n:n['score'],reverse=True)
        if not sample:continue
        threshold=sample[max(0,math.ceil(len(sample)*analysis['top_pct']/100)-1)]['score']
        chosen={n['id'] for n in sample if n['score']>=threshold}
        sensitivity.append({'excluded':excluded,'retained':len(chosen&baseline),'baseline':len(baseline),
                            'retention_pct':len(chosen&baseline)/len(baseline)*100 if baseline else None})
    return {'distribution':{k:quantiles([n[k] for n in notes if n.get(k) is not None]) for k in ['likes','favorites','comments','followers','score']},
            'sensitivity':sensitivity,'note':'删除一个维度后在相同可评分记录中重新归一化排名；保留率衡量敏感性，不是预测准确率。未提供真实层级标签，不报告准确率或召回率。'}
