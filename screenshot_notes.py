"""Local Windows OCR and isolated, reference-calibrated note scoring."""
import base64
import bisect
import datetime as dt
import io
import json
import math
from pathlib import Path
import re
import statistics
import subprocess
import tempfile
from PIL import Image,ImageOps
from scoring import DEFAULT_WEIGHTS,DEFINITIONS

ROOT=Path(__file__).resolve().parent

def compact(text):
    return re.sub(r'(?<=[\u3400-\u9fff#])\s+|\s+(?=[\u3400-\u9fff])','',text).strip()

REGIONS = {
    'author': ('作者区', (0, .035, 1, .16)),
    'title': ('标题区', (0, .48, 1, .90)),
    'body': ('正文区', (0, .54, 1, .92)),
    'tags': ('标签区', (0, .62, 1, .92)),
    'likes': ('点赞区', (.40, .86, .62, 1)),
    'favorites': ('收藏区', (.58, .86, .82, 1)),
    'comments': ('评论区', (.78, .86, 1, 1)),
    'content_image': ('内容图片区', (0, .13, 1, .78)),
}

def _run_ocr(path):
    try:
        proc=subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'screenshot_ocr.ps1'),'-ImagePath',str(path)],capture_output=True,timeout=45,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except (FileNotFoundError,subprocess.TimeoutExpired):raise ValueError('本地 OCR 不可用或超时。可在表单中手动填写识别信息。') from None
    if proc.returncode:raise ValueError('本地 OCR 识别失败，请确认 Windows 已安装中文 OCR 语言包；可手动填写。')
    return json.loads(proc.stdout.decode('utf-8-sig'))

def _region_text(result):
    return [compact(line['text']) for line in result.get('lines',[]) if compact(line['text'])]

def _region_records(result):
    records=[]
    for line in result.get('lines',[]):
        text=compact(line.get('text',''));words=line.get('words',[])
        if text and words:records.append({'text':text,'font':statistics.median(w['height'] for w in words),'y':min(w['y'] for w in words)})
    return records

def _number_in_region(lines):
    candidates=[]
    for text in lines:
        candidates.extend(re.findall(r'(?<!\d)(\d+(?:\.\d+)?[万千wWkK]?)(?!\d)',text))
    return candidates[-1] if candidates else ''

def parse_regions(results, width, height):
    region_data={};region_records={}
    for key,(label,box) in REGIONS.items():
        records=_region_records(results[key]);lines=[x['text'] for x in records];region_records[key]=records
        region_data[key]={'label':label,'box':[round(v,3) for v in box],'text':'\n'.join(lines),'lines':lines}
    fields={k:'' for k in ['title','author','content','cover_text','tags','publish_time','date_visible','likes','favorites','comments','followers']}
    author=[x for x in region_data['author']['lines'] if len(x)>=2 and not re.search(r'关注|返回|\d{1,2}:\d{2}|5G|WiFi',x,re.I)]
    if author:fields['author']=author[0]
    title_source=region_records['title']
    candidates=[(i,x) for i,x in enumerate(title_source) if len(x['text'])>5 and not x['text'].startswith('#') and not re.search(r'关注|猜你想搜|说点什么|编辑|发布于',x['text'])]
    if candidates:
        start,chosen=max(candidates,key=lambda pair:pair[1]['font']);fields['title']=chosen['text']
        if start+1<len(title_source) and len(title_source[start+1]['text'])<=4 and title_source[start+1]['font']>=chosen['font']*.6:fields['title']+=title_source[start+1]['text']
    body_lines=[x for x in region_data['body']['lines'] if not re.search(r'关注|猜你想搜|说点什么|不喜欢|编辑|发布于',x)]
    title_start=next((i for i,x in enumerate(body_lines) if fields['title'].startswith(x)),None)
    if title_start is not None:
        body_lines=body_lines[title_start+1:]
        if body_lines and len(body_lines[0])<=4 and fields['title'].endswith(body_lines[0]):body_lines.pop(0)
    fields['content']='\n'.join(x for x in body_lines if '#' not in x)
    tag_lines=region_data['tags']['lines']
    meta=next((i for i,x in enumerate(tag_lines) if re.search(r'猜你想搜|说点什么|编辑|发布于|不喜|不欢',x)),len(tag_lines))
    tag_lines=tag_lines[:meta];hash_start=next((i for i,x in enumerate(tag_lines) if '#' in x),None)
    if hash_start is not None:
        hash_text=''.join(tag_lines[hash_start:])
        fields['tags']=','.join(x.strip() for x in hash_text.split('#')[1:] if x.strip())
    cover_lines=region_data['content_image']['lines'];title_mark=next((i for i,x in enumerate(cover_lines) if re.search(r'Mark|适合送',x,re.I)),len(cover_lines))
    fields['cover_text']='\n'.join(cover_lines[:title_mark])
    for key in ['likes','favorites','comments']:fields[key]=_number_in_region(region_data[key]['lines'])
    date_lines=[]
    for key in ['body','tags']:
        date_lines.extend(x for x in region_data[key]['lines'] if re.search(r'编辑[于干]|发布于',x))
    fields['date_visible']='；'.join(dict.fromkeys(date_lines))
    # OCR never promotes dates to publish_time. That optional field is manual and must be a confirmed full date.
    evidence={k:f"来自{REGIONS[k][0]}，请对照截图核对" for k in ['author','title','likes','favorites','comments'] if fields.get(k)}
    warnings=['已按作者、标题、正文、标签、互动数字和内容图片分区识别。区域可能因截图版式不同而偏移，请逐项核对。',
              '手机状态栏时间、图片内日期和“编辑于”信息均不自动写入发布日期；发布日期只能由用户确认后可选补充。',
              '粉丝数为可选补充字段，不从截图内其他数字推断。']
    return {'fields':fields,'evidence':evidence,'warnings':warnings,'regions':region_data,
            'raw_lines':[f"【{v['label']}】\n{v['text']}" for v in region_data.values()],
            'engine':'Windows OCR zh-Hans-CN · 分区识别','image_size':[width,height]}

def parse_ocr(result):
    width,height=result['width'],result['height'];lines=[]
    for line in result['lines']:
        words=line.get('words',[])
        if not words:continue
        lines.append({'text':compact(line['text']),'x':min(w['x'] for w in words),'y':min(w['y'] for w in words),
                      'font':statistics.median(w['height'] for w in words),'words':words})
    lines.sort(key=lambda l:l['y'])
    fields={k:'' for k in ['title','author','content','cover_text','tags','publish_time','date_visible','likes','favorites','comments','followers']}
    evidence={};warnings=['OCR 可能误识别数字与文字，请逐项核对后计算。截图不能验证笔记真实性或实时数据。']
    candidates=[w for l in lines for w in l['words'] if w['y']>height*.86 and w['x']>width*.43 and re.fullmatch(r'\d+(?:\.\d+)?[万千wWkK]?',w['text'])]
    if candidates:
        font=statistics.median(w['height'] for w in candidates)
        candidates=[w for w in candidates if .65*font<=w['height']<=1.45*font]
        latest=max((w['y'] for w in candidates),default=0)
        candidates=[w for w in candidates if abs(w['y']-latest)<height*.022]
        regions={'likes':(.43,.66),'favorites':(.66,.85),'comments':(.85,1)}
        for key,(left,right) in regions.items():
            found=[w for w in candidates if left<=w['x']/width<right]
            if len(found)==1:
                fields[key]=found[0]['text'];evidence[key]=f"底部互动栏候选，坐标 ({found[0]['x']},{found[0]['y']})，需核对图标归属"
    author=next((l for l in lines if .065*height<l['y']<.15*height and .16*width<l['x']<.5*width and len(l['text'])>=2 and not re.search(r'关注|返回|\d{2}:',l['text'])),None)
    if author:fields['author']=author['text'];evidence['author']='截图顶部作者栏候选，内嵌截图的署名不合并'
    possible=[l for l in lines if .3*height<l['y']<.87*height and len(l['text'])>8 and not l['text'].startswith('#') and not re.search(r'猜你想搜|说点什么|编辑|发布于',l['text'])]
    title=max(possible,key=lambda l:l['font'],default=None)
    if title:
        fields['title']=title['text'];evidence['title']='较大字号标题候选；换行或裁切可能导致不完整'
        end=min([l['y'] for l in lines if l['y']>title['y'] and re.search(r'猜你想搜|说点什么|编辑|发布于',l['text'])]+[height*.89])
        remaining=[l for l in lines if title['y']<l['y']<end]
        if remaining and len(remaining[0]['text'])<=6 and remaining[0]['font']>=title['font']*.9 and remaining[0]['y']-title['y']<title['font']*3:
            fields['title']+=remaining.pop(0)['text']
        body=[l['text'] for l in remaining if not (l['x']>width*.8 and len(l['text'])<5)]
        fields['content']='\n'.join(body)
        covers=[l['text'] for l in lines if height*.2<l['y']<title['y'] and len(l['text'])>5 and not re.search(r'关注|White Peak',l['text'],re.I)]
        fields['cover_text']='\n'.join(covers)
        hashtext=''.join(l for l in body if '#' in l or (body.index(l)>0 and '#' in body[body.index(l)-1]))
        fields['tags']=','.join(t.strip() for t in hashtext.split('#')[1:] if t.strip())
    date_lines=[l['text'] for l in lines if re.search(r'编辑|发布于|\d{4}[-/]\d',l['text']) and l['y']>height*.5]
    fields['date_visible']='；'.join(date_lines)
    for line in date_lines:
        match=re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})',line)
        if match and '发布于' in line and '编辑' not in line:
            try:fields['publish_time']=dt.datetime.strptime(match[1].replace('/','-'),'%Y-%m-%d').date().isoformat()
            except ValueError:pass
    if not fields['publish_time']:warnings.append('未确认完整发布日期。手机状态栏时间、编辑日期和缺少年份的月日均不自动用于速度计算。')
    warnings.append('粉丝数不从截图内其他数字推断，请自行核对补充。')
    return {'fields':fields,'evidence':evidence,'warnings':warnings,'raw_lines':[l['text'] for l in lines],
            'engine':result['engine'],'image_size':[width,height]}

def recognize_image(data):
    if len(data)>10_000_000:raise ValueError('单张图片不能超过 10 MB。')
    try:
        img=Image.open(io.BytesIO(data))
        if img.format not in ['JPEG','PNG','WEBP']:raise ValueError('仅支持 JPG、PNG、WebP 图片。')
        if img.width*img.height>30_000_000:raise ValueError('图片超过 3000 万像素，请截取笔记区域。')
        img=ImageOps.exif_transpose(img).convert('RGB');img.thumbnail((2500,2500))
    except (OSError,Image.DecompressionBombError):raise ValueError('无法解码图片，请上传有效截图。') from None
    with tempfile.TemporaryDirectory(prefix='xhs-ocr-') as tmp:
        results={}
        for key,(_,bounds) in REGIONS.items():
            x1,y1,x2,y2=bounds
            crop=img.crop((int(img.width*x1),int(img.height*y1),int(img.width*x2),int(img.height*y2)))
            path=Path(tmp)/f'{key}.png';crop.save(path)
            results[key]=_run_ocr(path)
        return parse_regions(results,img.width,img.height)

def appreciate(fields):
    title=str(fields.get('title','')).strip();content=str(fields.get('content','')).strip()
    tags=str(fields.get('tags','')).strip();visual=str(fields.get('cover_text','')).strip();all_text='\n'.join([title,content,tags,visual])
    if not any([title,content,tags,visual]):raise ValueError('请至少核对并填写标题、正文、标签或图片文字中的一项。')
    specs=[
      ('title_attraction','标题吸引力',title,[(r'\?|？|!|！|谁懂|救命|心动|绝了|Mark|清单|推荐',18),(r'\d+',8),(r'送|自用|朋友|通勤|租房|餐桌',12)]),
      ('favorite_intent','收藏倾向',all_text,[(r'Mark|收藏|清单|合集|推荐|攻略|避雷',24),(r'\d+|款|种|个',10),(r'适合|值得|实用|下单',12)]),
      ('visual_expression','视觉表达',visual or all_text,[(r'色|配色|釉|纹理|质感|光|构图|画面|高颜值',20),(r'像|仿佛|莫奈|油画|梦幻|氛围',18),(r'上半|下半|边|局部|细节',12)]),
      ('scene','场景感',all_text,[(r'送|礼物|朋友|自用|餐桌|早餐|下午茶|咖啡|家里|通勤|租房',24),(r'适合|时候|场景',10)]),
      ('selling_points','产品卖点',all_text,[(r'实用|材质|尺寸|容量|手工|设计|釉|耐用|好洗|防滑',22),(r'颜色|造型|细节|质感|功能',14)]),
      ('interaction','互动引导',content,[(r'你们|你会|你喜欢|评论|留言|告诉我|选哪个|有没有|求推荐',32),(r'\?|？',10)])
    ]
    items=[]
    for key,label,text,rules in specs:
        score=35 if text else 0;evidence=[]
        for pattern,points in rules:
            match=re.search(pattern,text,re.I)
            if match:score+=points;evidence.append(match.group(0))
        if text:score+=min(15,len(text)//35*3)
        items.append({'key':key,'label':label,'score':min(100,score),'evidence':'、'.join(dict.fromkeys(evidence)) or '未发现明显信号',
                      'suggestion':{'title_attraction':'补充具体对象、利益点或反差 Hook。','favorite_intent':'增加清单价值、选择标准或可复用信息。','visual_expression':'描述颜色、材质、局部细节和画面联想。','scene':'说清谁在什么情境下使用或赠送。','selling_points':'把审美感受落到真实、可核对的产品特点。','interaction':'结尾加入与内容相关、容易回答的问题。'}[key]})
    return {'score':round(sum(x['score'] for x in items)/len(items),1),'items':items,'method':'本地可解释规则鉴赏；依据当前核对后的标题、正文、标签和图片文字，不需要粉丝数或发布日期。分数用于发现内容结构，不代表平台推荐概率。'}

def score_external(fields,reference,parse_number):
    if not str(fields.get('title','')).strip():raise ValueError('请核对并填写标题。')
    raw={k:parse_number(fields.get(k)) for k in ['likes','favorites','comments','followers']}
    for k in raw:
        if fields.get(k) not in ('',None) and raw[k] is None:raise ValueError(f'{k} 格式无效，请填写非负数或“1.2万”。')
    n={**fields,**raw,'velocity':None,'engagement_rate':None,'favorite_value':None,'popularity':raw['likes'],'comment':raw['comments']}
    complete=all(raw[k] is not None for k in ['likes','favorites','comments'])
    if raw['likes'] is not None and raw['favorites'] is not None:n['favorite_value']=raw['favorites']/(raw['likes']+1)
    if complete and raw['followers'] is not None and raw['followers']>0:n['engagement_rate']=sum(raw[k] for k in ['likes','favorites','comments'])/raw['followers']
    if fields.get('publish_time'):
        try:age=(dt.date.fromisoformat(reference['as_of'])-dt.date.fromisoformat(fields['publish_time'])).days
        except ValueError:raise ValueError('发布日期必须包含完整年份，格式为 YYYY-MM-DD。') from None
        if age<0:raise ValueError('发布日期晚于数据统计日期，请检查日期。')
        n['age_days']=age
        if complete:n['velocity']=sum(raw[k] for k in ['likes','favorites','comments'])/(age+1)
    used={k:w for k,w in DEFAULT_WEIGHTS.items() if n.get(k) is not None}
    missing=[k for k in DEFAULT_WEIGHTS if k not in used]
    peers=[p for p in reference['notes'] if all(p.get(k) is not None for k in used)] if used else []
    components={};parts={};total=sum(used.values())
    if len(peers)>=2:
        for k,w in used.items():
            vals=sorted(p[k] for p in peers)
            def percentile(v):
                left=bisect.bisect_left(vals,v);right=bisect.bisect_right(vals,v)
                if left!=right:rank=(left+right-1)/2
                else:rank=left-.5
                return min(100,max(0,rank/(len(vals)-1)*100))
            components[k]=percentile(n[k]);parts[k]=components[k]*w/total
    score=sum(parts.values()) if parts else None
    return {'note':n,'score':score,'status':'完整 ViralScore' if not missing and score is not None else '部分维度参考分' if score is not None else '无法评分',
            'missing':missing,'weights':{k:w/total for k,w in used.items()} if total else {},'components':components,'parts':parts,
            'reference_count':len(peers),'as_of':reference['as_of'],'definitions':DEFINITIONS,
            'method':'固定参照集；使用默认五维权重。缺失维度移除后重新归一化，部分分数不能与完整分数直接比较。截图不加入参照集。外部值取参照平均秩或相邻位置中点，边界截到 0–100。',
            'advice':borrowing_advice(n)}

def borrowing_advice(n):
    title=n['title'];text=str(n.get('content',''))+'\n'+str(n.get('cover_text',''));items=[]
    for pattern,label,suggestion in [
        (r'送|礼物','选题场景','可借鉴“给谁用／送给谁”的明确场景，换成你产品的真实适用对象。'),
        (r'莫奈|睡莲|油画|梦幻','视觉联想','用具体艺术或色彩联想解释视觉感受；属于文案表达，不据此认定产品工艺。'),
        (r'釉|配色|颜色|波浪|描边','细节描述','结合自己拍到的局部细节描述颜色、形状与搭配，不照搬参考产品参数。'),
        (r'Mark|收藏|清单|推荐','标题表达','把“收藏理由＋具体品类”作为标题方向，并给读者明确的选择价值。')]:
        evidence=next((line for line in (title+'\n'+text).splitlines() if re.search(pattern,line,re.I)),None)
        if evidence:items.append({'name':label,'evidence':evidence,'suggestion':suggestion})
    if not items:items.append({'name':'内容补充','evidence':title,'suggestion':'截图信息不足以总结完整结构，请补充正文或人工说明。'})
    return items
