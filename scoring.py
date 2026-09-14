"""ViralScore v2: comparable 0–100 percentile dimensions."""
import bisect
import math

DEFAULT_WEIGHTS={'popularity':25,'engagement_rate':25,'favorite_value':25,'velocity':15,'comment':10}
DEFINITIONS={
    'popularity':'点赞数，作为热度代理，不代表曝光量',
    'engagement_rate':'(点赞 + 收藏 + 评论) / 粉丝数；粉丝必须大于 0',
    'favorite_value':'收藏 / (点赞 + 1)，使用 +1 平滑零点赞分母',
    'velocity':'(点赞 + 收藏 + 评论) / (发布后自然天数 + 1)',
    'comment':'评论数',
}
STRENGTH_LABELS={
    'popularity':'绝对点赞热度高','engagement_rate':'小粉丝高互动','favorite_value':'高收藏率',
    'velocity':'互动增长速度快','comment':'评论活跃度高'
}

def score_notes(notes,mapping,weights=None):
    weights=DEFAULT_WEIGHTS if weights is None else weights
    if any(k not in DEFAULT_WEIGHTS for k in weights): raise ValueError('评分配置已升级，请刷新页面使用新版五项权重。')
    if any(not math.isfinite(float(v)) or float(v)<0 for v in weights.values()): raise ValueError('权重必须为有限非负数。')
    needed={'popularity':['likes'],'engagement_rate':['likes','favorites','comments','followers'],
            'favorite_value':['likes','favorites'],'velocity':['likes','favorites','comments','publish_time'],'comment':['comments']}
    active={k:float(weights.get(k,0)) for k,fields in needed.items() if all(mapping.get(f) for f in fields) and float(weights.get(k,0))>0}
    if not active: raise ValueError('至少映射一个可计算的评分维度，并设置正权重。')
    weight_sum=sum(active.values()); active={k:v/weight_sum for k,v in active.items()}
    for note in notes:
        note['popularity']=note['likes'];note['comment']=note['comments']
        note['favorite_value']=note['favorites']/(note['likes']+1) if note['likes'] is not None and note['favorites'] is not None else None
        note.update(score=None,parts={},components={},high=False)
        note['score_missing']=[k for k in active if note[k] is None]
    eligible=[n for n in notes if not n['score_missing']]
    if len(eligible)>1:
        for key,weight in active.items():
            values=sorted(n[key] for n in eligible)
            for n in eligible:
                rank=(bisect.bisect_left(values,n[key])+bisect.bisect_right(values,n[key])-1)/2
                n['components'][key]=100*rank/(len(values)-1)
                n['parts'][key]=n['components'][key]*weight
        for n in eligible: n['score']=sum(n['parts'].values())
    for note in notes:
        ranked=sorted(note['components'],key=lambda k:note['components'][k],reverse=True)
        strong=[STRENGTH_LABELS[k] for k in ranked if note['components'][k]>=70][:2]
        if not strong and ranked:strong=[STRENGTH_LABELS[ranked[0]]]
        note['strengths']=strong
        note['score_summary']='主要优势：'+' + '.join(strong) if strong else '当前没有足够维度形成优势判断'
    return active

def association(a,h,b,o):
    """Lift = P(high | feature) / P(high), within analyzed observations only."""
    high_pct=a/h*100 if h else None; other_pct=b/o*100 if o else None
    lift=(a/(a+b))/(h/(h+o)) if h and o and a+b else None
    diff=high_pct-other_pct if high_pct is not None and other_pct is not None else None
    direction='无法判断' if lift is None else '正关联' if lift>1+1e-9 else '负关联' if lift<1-1e-9 else '无差异'
    return {'lift':lift,'difference_pp':diff,'association':direction,'support':a+b,
            'high_pct':high_pct,'other_pct':other_pct,'caution':'样本内描述性关联，非因果或显著性结论；小样本需谨慎。'}
