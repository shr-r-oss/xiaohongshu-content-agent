"""Evidence-based category retrieval and local drafting, independent of LLM calls."""
import re
from collections import Counter
from scoring import association
from difflib import SequenceMatcher

CATEGORIES = {
    '创意餐盘': ['餐盘','盘子','手作盘','陶瓷盘','碟子','果盘','点心盘'],
    '杯碗茶具': ['杯','碗','茶具','茶壶'],
    '托盘与收纳': ['托盘','收纳','置物'],
    '餐桌布艺': ['餐垫','桌布','布艺'],
    '桌面摆件': ['摆件','花瓶','装饰物'],
    '厨房小物': ['厨房','厨具','勺','筷','调味','开瓶'],
}
CATEGORY_ALIASES={'托盘收纳':'托盘与收纳'}
HOOKS = [('情绪惊叹', r'救命|神仙|谁懂|心动|惊艳|绝了|太会|拿捏'),
         ('清单数字', r'\d+\s*[个件款种]|清单|合集'),
         ('场景代入', r'餐桌|早餐|下午茶|周末|租房|独居|咖啡'),
         ('发现分享', r'发现|分享|挖到|淘到|宝藏|小众'),
         ('提问悬念', r'什么|怎么|为什么|[？?]')]
SCENES = ['下午茶','早餐','周末','节日布置','独居','租房','咖啡','露营','甜品时间','聚会']
STRUCTURES = [('场景开头',r'下午茶|早餐|周末|节日|咖啡|餐桌'),
              ('细节分点',r'(?:^|\n)\s*[·•\-]|配色|釉面|纹理|尺寸'),
              ('适用场景',r'适合|放在|搭配|场景'),
              ('结尾互动',r'你们|评论|留言|你喜欢|告诉我')]

def tags(note):
    return set(CATEGORY_ALIASES.get(t.strip().lstrip('#'),t.strip().lstrip('#')) for t in re.split(r'[,，#\s]+',note.get('tags','')) if t.strip())

def similarity(note,topic,category):
    product=' '.join(re.findall(r'「([^」]+)」',note.get('content','')))
    text=note['title']+' '+product
    parts=[topic[i:i+2] for i in range(max(0,len(topic)-1))]
    matches=list(dict.fromkeys(p for p in parts if p in text))
    topic_specific=[p for p in matches if p not in CATEGORIES.get(category,[])]
    score=(5 if topic in text else 0)+len(matches)+2*len(topic_specific)
    reasons=[f'同属 {category}']
    if matches: reasons.append('标题或产品名匹配：'+'、'.join(matches))
    else: reasons.append('仅类别相似，未命中主题词组')
    return {'similarity':score,'match_terms':matches,'match_reasons':reasons,'direct_match':bool(matches)}

def excerpt(text, pattern):
    return next((line.strip() for line in re.split(r'[\n。！？]',text) if re.search(pattern,line)), '')

def retrieve(notes, topic, category=''):
    inferred = category or next((name for name,words in CATEGORIES.items() if any(word in topic for word in words)), '')
    if category and category not in CATEGORIES: raise ValueError('请选择支持的类别或自动匹配。')
    matched=[]
    for note in notes:
        note_tags=tags(note)
        if inferred:
            # Explicit category labels take precedence over mentions in generic prose.
            explicit=note_tags.intersection(CATEGORIES)
            ok=inferred in explicit if explicit else any(w in note['title'] for w in CATEGORIES[inferred])
        else:
            ok=topic.lower() in (note['title']+' '+note.get('tags','')).lower()
        if ok: matched.append(note)
    return inferred or '关键词精确匹配',matched

def summarize(group,other,rules,text_fn):
    rows=[]
    for label,pattern in rules:
        hits=[n for n in group if re.search(pattern,text_fn(n))]
        controls=[n for n in other if re.search(pattern,text_fn(n))]
        rows.append({'name':label,'count':len(hits),'total':len(group),
                     'other_count':len(controls),'other_total':len(other),**association(len(hits),len(group),len(controls),len(other)),
                     'examples':[{'id':n['id'],'quote':excerpt(text_fn(n),pattern)} for n in hits[:2]]})
    return sorted(rows,key=lambda row:row['count'],reverse=True)

def generate_plan(analysis, topic, audience='', brief='', category=''):
    topic=str(topic).strip()
    if not topic or len(topic)>100: raise ValueError('请输入 1–100 字的产品主题。')
    name,matched=retrieve(analysis['notes'],topic,category)
    matched=[dict(n,**similarity(n,topic,name)) for n in matched]
    high=[n for n in matched if n.get('high') and n.get('score') is not None]
    other=[n for n in matched if not n.get('high') and n.get('score') is not None]
    base={'topic':topic,'category':name,'audience':str(audience)[:500],'brief':str(brief)[:2000],
          'matched_count':len(matched),'high_count':len(high),'other_count':len(other),
          'similar_count':sum(n['direct_match'] for n in matched),'similar_high_count':sum(n['direct_match'] for n in high),
          'matched_ids':[n['id'] for n in matched],
          'as_of':analysis['as_of'],'top_pct':analysis['top_pct'],
          'selection':'沿用当前筛选范围与 ViralScore 高表现标记，再按类别检索；原工作表标签不参与判定。',
          'hooks':[],'structures':[],'tags':[],'scenes':[],'references':[],'plans':[],'advice':[]}
    if not high:
        return dict(base,status='insufficient',message='当前范围没有匹配主题的高表现笔记。请切换类别、调整排行筛选或补充数据；未使用无关类别替代生成。')
    hooks=summarize(high,other,HOOKS,lambda n:n['title'])
    structures=[]
    for label,pattern in STRUCTURES:
        def selected_text(n):
            body=n.get('content','')
            paragraphs=[p for p in body.split('\n\n') if p.strip() and not p.lstrip().startswith('#')]
            if not paragraphs: return ''
            return paragraphs[0] if label=='场景开头' else paragraphs[-1] if label=='结尾互动' else body
        structures.extend(summarize(high,other,[(label,pattern)],selected_text))
    scenes=summarize(high,other,[(s,re.escape(s)) for s in SCENES],lambda n:n['title']+'\n'+n.get('content',''))
    tag_counts=Counter(t for n in high for t in tags(n))
    tag_rows=[{'name':t,'count':c,'total':len(high),'other_count':sum(t in tags(n) for n in other),'other_total':len(other),**association(c,len(high),sum(t in tags(n) for n in other),len(other))} for t,c in tag_counts.most_common(8)]
    high.sort(key=lambda n:(n['similarity'],n['score']),reverse=True)
    # Limit repetitive author/style examples to leave room for other writing approaches.
    diverse=[];authors={}
    for n in high:
        author=n.get('author') or n['id']
        if authors.get(author,0)>=2:continue
        if any(SequenceMatcher(None,n.get('content',''),x.get('content','')).ratio()>.9 for x in diverse):continue
        diverse.append(n);authors[author]=authors.get(author,0)+1
        if len(diverse)==6:break
    refs=[{k:n.get(k) for k in ['id','title','content','score','high','similarity','match_reasons','match_terms']} for n in diverse]
    scene=next((r['name'] for r in scenes if r['count']),None)
    hook=next((r for r in sorted(hooks,key=lambda r:(r['lift'] or 0,r['count']),reverse=True) if r['count']>=3 and r['lift'] is not None and r['lift']>1),None)
    chosen_tags=[r['name'] for r in tag_rows[:5]]
    scene_text=scene or '你实际使用的场景'
    audience=str(audience).strip() or '对这个品类感兴趣的读者'
    advice=[f'当前类别命中 {len(matched)} 篇，其中 {len(high)} 篇符合当前高表现判定。以下频次只描述此类别。',
            (f'标题可优先试验“{hook["name"]}”表达，命中 {hook["count"]}/{len(high)} 篇；保留真实语气，不照搬原题。' if hook else '标题未命中预设 Hook 词典，建议结合参考标题人工判断。'),
            (f'可考虑“{scene}”场景，命中 {scenes[0]["count"]}/{len(high)} 篇；只有与你的产品实际用途一致时才采用。' if scene else '未提取到常见场景，请先明确产品实际使用场景。'),
            '正文结构特征来自规则匹配，按“开头—细节—适用场景—收尾”建议组织，不宣称所有样本都采用同一顺序。',
            '补充自己的图片、尺寸、材质和实际体验；不从参考笔记复制产品参数或使用经历。']
    if len(high)<5: advice.append('该类别高表现样本不足 5 篇，规律仅为探索线索。')
    if not any(n.get('content') for n in high): advice.append('参考笔记缺少正文：正文结构与场景证据不足，以下正文仅为写作框架。')
    plans=[]
    angles=['场景种草','细节观察','选购参考']
    for i,angle in enumerate(angles):
        if angle=='场景种草':
            titles=[f'{topic}灵感｜从{scene_text}开始布置',f'想给{scene_text}添点变化？看看{topic}',f'{topic}，让日常多一个认真摆放的理由']
            opening=f'如果你也想让{scene_text}多一点自己的风格，可以先从一件{topic}开始。'
        elif angle=='细节观察':
            titles=[f'{topic}怎么选？先看这3处细节',f'关于{topic}，我想认真聊聊这些细节',f'不只看外形：{topic}的观察清单']
            opening=f'选{topic}的时候，除了第一眼的外形，我也想把细节看清楚。'
        else:
            titles=[f'挑{topic}前，先问自己3个问题',f'给{audience}的{topic}选择思路',f'{topic}值得入手吗？从使用需求开始判断']
            opening=f'{topic}是不是适合自己，我更想从使用需求开始判断。'
        if hook:
            hook_title={
                '情绪惊叹':f'谁懂！想把{topic}的这些细节认真拍下来',
                '清单数字':f'{topic}的3个观察角度，挑选前先看看',
                '场景代入':f'{scene_text}灵感｜{topic}可以怎么搭',
                '发现分享':f'好物分享｜关于{topic}的挑选灵感',
                '提问悬念':f'{topic}怎么选，才适合自己的日常？',
            }
            titles[0]=hook_title[hook['name']] if i==0 else titles[0]
        text=(opening+f'\n\n这次准备分享的是【填写具体款式】，想放在{scene_text}使用。'
              '\n\n· 外观：填写实物颜色、纹理与照片对应的细节。'
              '\n· 使用：填写核实后的尺寸、容量或摆放方式。'
              '\n· 取舍：填写真实优点，以及需要接受的限制。'
              f'\n\n如果你也关注{topic}，可以先结合自己的空间和使用频率考虑，再决定是否适合。'
              '\n\n你挑这类好物时，最在意外形、实用性，还是搭配方式？'
              '\n\n'+' '.join('#'+t for t in chosen_tags))
        if angle=='细节观察':
            text=(opening+'\n\n先把这件【填写具体款式】放在真实光线下，再对照下面三个角度记录。'
                  '\n\n1. 视觉细节：【补充与实物照片一致的配色、纹理或造型】。'
                  '\n2. 使用细节：【补充已核实的尺寸、重量或清洁方式】。'
                  '\n3. 搭配细节：【补充与现有物品的实际搭配效果】。'
                  '\n\n这些细节里，哪些是自己需要的，哪些只是第一眼吸引？想清楚以后再做选择。'
                  '\n\n你会先看哪一项？\n\n'+' '.join('#'+t for t in chosen_tags))
        elif angle=='选购参考':
            text=(opening+f'\n\n给同样关注{topic}的你，整理三个选购前可以问自己的问题。'
                  f'\n\n① 准备用在哪里？比如{scene_text}，先确认空间和使用频率。'
                  '\n② 哪些条件不能妥协？【补充已核实的尺寸、材质、预算及适用限制】。'
                  '\n③ 能接受哪些取舍？【补充产品真实限制，避免只写优点】。'
                  '\n\n把答案和具体款式一一对照，比只凭一张好看的照片做决定更清楚。'
                  '\n\n你选这类好物时，有什么必看条件？\n\n'+' '.join('#'+t for t in chosen_tags))
        plans.append({'angle':angle,'topic':f'{topic} · {angle}','titles':titles,'opening':opening,'body':text,
                      'strategy':{'audience':audience,'objective':{'场景种草':'通过具体使用场景建立代入感','细节观察':'帮助读者观察与比较产品细节','选购参考':'给出可执行的选择问题和取舍框架'}[angle],
                                  'thesis':f'围绕{topic}，从{angle}切入，解释为什么值得关注以及适用条件。',
                                  'evidence':f'类别样本 {len(matched)} 篇 / 高表现 {len(high)} 篇；'+(f'{hook["name"]} Lift {hook["lift"]:.2f}（样本内关联）' if hook else '没有支持充分的正关联 Hook，采用探索性表达'),
                                  'difference':angles[i]+'视角，避免三套方案只替换同义词'},
                      'outline':['场景或需求开头','产品真实信息','3 项可核实细节','适用条件与取舍','开放式提问'],
                      'tags':chosen_tags,'scene':scene_text,'reference_ids':[n['id'] for n in refs[:3]],
                      'basis':f'参考类别：{name}；标题线索：{hook["name"] if hook else "未检出"}；场景线索：{scene or "未检出"}。框架为本地组合，不是模型推理。',
                      'visuals':['产品整体与实际场景','能支撑正文细节的近景','尺寸或实际摆放对照'],
                      'validation':'核实占位信息后发布；在相同观察时长内比较标题及互动表现。'})
    return dict(base,status='ready',mode='本地证据检索 + 规则生成（非 AI）',hooks=hooks,structures=structures,
                scenes=scenes,tags=tag_rows,references=refs,plans=plans,advice=advice)
