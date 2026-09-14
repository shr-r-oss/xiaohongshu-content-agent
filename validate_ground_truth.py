"""Validate frozen ViralScore v2 against supplied labels; never fit weights."""
import csv,json,datetime as dt,statistics,math
from collections import Counter
from pathlib import Path
import app

ROOT=Path(__file__).resolve().parent
truth=list(csv.DictReader((ROOT/'ground_truth.csv').open(encoding='utf-8-sig')))
file=ROOT/'小红书好物分享500模拟数据.csv'
data=app.read_file(file.read_bytes(),file.name)
raw={row['id']:row for sheet in data['sheets'] for row in sheet['rows']}
assert len({r['id'] for r in truth})==len(truth),'Duplicate truth IDs'
assert len(raw)==sum(len(s['rows']) for s in data['sheets']),'Duplicate source IDs'
assert set(raw)=={r['id'] for r in truth},'ID mismatch'
dates=Counter(str(dt.datetime.fromisoformat(raw[t['id']]['publish_time']).date()+dt.timedelta(days=int(t['age_days']))) for t in truth)
lower=max(dt.datetime.fromisoformat(raw[t['id']]['publish_time'])+dt.timedelta(days=int(t['age_days'])) for t in truth)
upper=min(dt.datetime.fromisoformat(raw[t['id']]['publish_time'])+dt.timedelta(days=int(t['age_days'])+1) for t in truth)
assert lower<upper,(lower,upper)
as_of=str(lower.date());data['as_of']=as_of
analysis=app.analyze(data)
joined=[dict(n,truth=next(t for t in truth if t['id']==n['id'])) for n in analysis['notes']]
order=['低表现','普通','中高表现','爆款','超级爆款']
tiers=Counter(n['truth']['performance_tier'] for n in joined)
assert set(tiers)<=set(order),tiers
positive={'爆款','超级爆款'}

def auc(rows,key):
    pos=[r[key] for r in rows if r['truth']['performance_tier'] in positive]
    neg=[r[key] for r in rows if r['truth']['performance_tier'] not in positive]
    return sum((a>b)+.5*(a==b) for a in pos for b in neg)/(len(pos)*len(neg)) if pos and neg else None
def metrics(rows,selected):
    tp=sum(n['id'] in selected and n['truth']['performance_tier'] in positive for n in rows)
    fp=sum(n['id'] in selected and n['truth']['performance_tier'] not in positive for n in rows)
    fn=sum(n['id'] not in selected and n['truth']['performance_tier'] in positive for n in rows)
    tn=len(rows)-tp-fp-fn
    p=tp/(tp+fp) if tp+fp else 0;r=tp/(tp+fn) if tp+fn else 0
    return dict(tp=tp,fp=fp,fn=fn,tn=tn,precision=p,recall=r,f1=2*p*r/(p+r) if p+r else 0,accuracy=(tp+tn)/len(rows))
def ranks(values):
    sorted_values=sorted(values)
    return [sum(x<v for x in sorted_values)+(sum(x==v for x in sorted_values)-1)/2 for v in values]
high={n['id'] for n in joined if n['high']}
checks={k:0 for k in ['engagement','engagement_rate','velocity','age_days']}
for n in joined:
    vals={'engagement':sum(n[k] for k in app.METRICS),'engagement_rate':n['engagement_rate'],'velocity':n['velocity'],'age_days':n['age_days']}
    for k,v in vals.items():
        if not math.isclose(v,float(n['truth'][k]),rel_tol=1e-9,abs_tol=1e-9):checks[k]+=1
summary={
    'source':file.name,'ground_truth':'ground_truth.csv','as_of':as_of,'rows':len(joined),'scored':analysis['scored'],
    'tier_counts':dict(tiers),'special_counts':dict(Counter(n['truth']['special_case'] for n in joined)),
    'metadata_mismatches':checks,'positive_labels':sorted(positive),'threshold':analysis['threshold'],
    'top20':metrics(joined,high),'roc_auc':auc(joined,'score'),
    'spearman_tier':statistics.correlation(ranks([n['score'] for n in joined]),ranks([order.index(n['truth']['performance_tier']) for n in joined])),
    'tiers':[], 'top_k':[], 'baselines':[], 'special_cases':[],
}
for tier in order:
    group=[n for n in joined if n['truth']['performance_tier']==tier]
    if group:summary['tiers'].append(dict(tier=tier,count=len(group),selected=sum(n['high'] for n in group),mean=statistics.mean(n['score'] for n in group),median=statistics.median(n['score'] for n in group),minimum=min(n['score'] for n in group),maximum=max(n['score'] for n in group)))
for k in [25,50,75,100,150]:
    selected={n['id'] for n in joined[:k]};summary['top_k'].append(dict(k=k,**metrics(joined,selected)))
for key in ['likes','favorites','engagement_rate','favorite_value','velocity','comments']:
    ranked=sorted(joined,key=lambda n:n[key],reverse=True);cut=ranked[99][key]
    selected={n['id'] for n in joined if n[key]>=cut}
    summary['baselines'].append(dict(metric=key,count=len(selected),auc=auc(joined,key),**metrics(joined,selected)))
for case in summary['special_counts']:
    group=[n for n in joined if n['truth']['special_case']==case]
    summary['special_cases'].append(dict(case=case,count=len(group),**metrics(group,high)))
def example(n):return dict(id=n['id'],title=n['title'],tier=n['truth']['performance_tier'],case=n['truth']['special_case'],score=n['score'],likes=n['likes'],followers=n['followers'],parts=n['parts'])
summary['false_positives']=[example(n) for n in joined if n['high'] and n['truth']['performance_tier'] not in positive]
summary['false_negatives']=[example(n) for n in joined if not n['high'] and n['truth']['performance_tier'] in positive]
import copy
from scoring import score_notes
aligned=copy.deepcopy(joined)
for n in aligned:n['velocity']=sum(n[k] for k in app.METRICS)/(int(n['truth']['age_days'])+1)
score_notes(aligned,data['mapping'])
aligned.sort(key=lambda n:n['score'],reverse=True)
cut=aligned[99]['score'];aligned_high={n['id'] for n in aligned if n['score']>=cut}
summary['time_alignment']={'compatible_snapshot_interval':[str(lower),str(upper)],'description':'ground_truth age_days compatible with elapsed 24-hour floor; app currently uses calendar-day difference. Main metrics retain app behavior.', 'aligned_metrics':metrics(aligned,aligned_high),'aligned_auc':auc(aligned,'score'),'changed_top100_ids':sorted(high.symmetric_difference(aligned_high))}
(ROOT/'ViralScore验证结果.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
with (ROOT/'ViralScore逐条验证.csv').open('w',encoding='utf-8-sig',newline='') as f:
    writer=csv.writer(f);writer.writerow(['id','performance_tier','special_case','ViralScore','predicted_high','actual_viral','result'])
    for n in joined:
        actual=n['truth']['performance_tier'] in positive
        writer.writerow([n['id'],n['truth']['performance_tier'],n['truth']['special_case'],n['score'],n['high'],actual,'TP' if n['high'] and actual else 'FP' if n['high'] else 'FN' if actual else 'TN'])
print(json.dumps(summary,ensure_ascii=False,indent=2))
