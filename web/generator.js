let generatorResult=null, generatorRequest=null, generatorStep=1;
function generatorNav(){return `<div class="workflow-tabs">${['① 需求','② 证据','③ 方案','④ 评估与成稿'].map((x,i)=>`<button data-generator-step="${i+1}" class="${generatorStep===i+1?'active':''}" ${(i>0&&!generatorResult)?'disabled':''}>${x}</button>`).join('')}</div>`}

function generatorView(){
    const g=generatorResult;
    return heading('Content Generator Agent','用户需求 → 同品类证据 → 三套方案 → 自评与优化 → 最终笔记')+generatorNav()+`
    <section data-generator-section="1" ${generatorStep===1?'':'hidden'}><div class="grid"><article class="panel"><h2>你想写什么好物？</h2>
      <div class="form-stack">
        <label>产品 / 主题<input id="product" maxlength="100" value="${esc(sessionStorage.getItem('product')||'手作餐盘')}" placeholder="例如：手作餐盘"></label>
        <label>参考类别<select id="generator-category"><option value="">自动匹配主题</option>${['创意餐盘','杯碗茶具','托盘与收纳','餐桌布艺','桌面摆件','厨房小物'].map(c=>`<option ${sessionStorage.getItem('generator-category')===c?'selected':''}>${c}</option>`).join('')}</select></label>
        <label>目标受众<input id="audience" value="${esc(sessionStorage.getItem('audience')||'喜欢餐桌美学的年轻人')}"></label>
        <label>账号定位 / 创作要求<textarea id="brief" placeholder="填写语气、用途、产品真实特点及禁用表达">${esc(sessionStorage.getItem('brief')||'分享有设计感的餐桌好物，语气自然，重视细节，不夸大产品效果。')}</textarea></label>
      <label>已知产品事实<textarea id="facts" placeholder="例如：小熊造型、实测直径、实际材质与使用体验。未核实的信息请勿填写为事实。">${esc(sessionStorage.getItem('facts')||'')}</textarea></label>
        <label><span><input type="checkbox" id="full-agent" ${status.connected?'':'disabled'}> 启用 LLM 全流程（意图、语义、生成、自评）</span></label>
        <label><span><input type="checkbox" id="auto-optimize" checked> LLM 生成后自动优化最佳方案一轮（本地模式也会执行一次规则自检与优化）</span></label>
        <p class="ai-note">启用后将发送主题、简报、产品事实、最多 24 篇同类对照笔记的 ID/标题/正文，以及草稿和评估意见。多阶段调用可能耗时数分钟。${status.connected?'':'AI 未连接，当前可运行本地评估与优化。'}</p>
      </div><div class="ai-actions"><button id="templates" class="primary">分析规律并生成方案</button></div>
      <p class="sub">未启用 LLM 时使用本地检索、规则草稿与规则评估；启用后执行模型全流程。没有同类样本时停止生成。</p>
      <p id="pipeline-progress" role="status"></p><p class="tip">沿用当前排行筛选、权重与前 ${result.top_pct}% 判定。正在研究 ${result.notes.length} 篇；统计日 ${result.as_of}。</p>
    </article><article class="panel"><h2>Agent 的工作过程</h2>
      <div class="step"><b>01</b><div>匹配主题与品类<p class="sub">手作餐盘 → 创意餐盘；已有类别标签优先。</p></div></div>
      <div class="step"><b>02</b><div>检索同类高表现笔记<p class="sub">显示类别命中、主题相似、高表现数量，解释每条证据的匹配原因。</p></div></div>
      <div class="step"><b>03</b><div>分析表达与场景<p class="sub">标题 Hook、正文特征、标签、场景，对照同类其余笔记。</p></div></div>
      <div class="step"><b>04</b><div>生成可编辑方案<p class="sub">生成三种切入角度，逐套评估后选择最佳方案；允许按建议自动优化，并记录前后评分。Generate → Evaluate → Refine。</p></div></div>
      <p class="sub">本地规则不会理解简报里的所有自由文本约束。需要复杂语气、禁用词和产品事实整合时，使用下方 AI 生成并复核。</p>
    </article></div></section>
    <div id="generator-output">${g?generatorOutput(g):'<div class="panel empty">填写主题后开始。你将看到参考依据和 3 套完整内容方案。</div>'}</div>`;
}

function evidenceTable(title,rows){
    return `<article class="panel"><h2>${title}</h2><p class="sub">高表现组命中 / 总数 · 同类别其余组对照；Lift 基于特征出现者的高表现比例与组内基准比例之比。</p>${rows.map(r=>`<div class="feature"><div class="panel-head" style="margin-bottom:5px"><strong>${esc(r.name)}</strong><span class="badge gray">${r.count}/${r.total} · 对照 ${r.other_count}/${r.other_total}</span></div>${r.lift!==undefined?`<p class="sub">${associationHtml(r)}</p>`:''}${(r.examples||[]).map(e=>`<div class="evidence">${esc(e.quote)} <button class="link" data-note="${esc(e.id)}">${esc(e.id)}</button></div>`).join('')}</div>`).join('')||'<p class="sub">无可用证据。</p>'}</article>`;
}

function generatorOutput(g){
    const top=`<article class="panel"><div class="panel-head"><div><h2>研究主题：${esc(g.topic)}</h2><p class="sub">匹配类别：${esc(g.category)} · 同类 ${g.matched_count} 篇 → 主题词组相似 ${g.similar_count??0} 篇 → 其中高表现 ${g.similar_high_count??0} 篇；同类高表现共 ${g.high_count} 篇</p></div><button id="generator-export">导出完整方案</button></div><p class="sub">${esc(g.selection)} 截至 ${esc(g.as_of)}，前 ${g.top_pct}%。</p></article>`;
    if(g.status!=='ready')return top+`<div class="tip">${esc(g.message)}</div>`;
    return top+`${g.pipeline_error?`<p class="tip">LLM 流程未完成：${esc(g.pipeline_error)}</p>`:''}<section data-generator-section="2" ${generatorStep===2?'':'hidden'}><article class="panel" style="margin-top:20px"><h2>Agent 总结 · 从证据到选题</h2><p class="sub">意图：${esc(g.intent?.goal||'')} · ${esc(g.intent?.mode||'')}</p><ul>${g.advice.map(a=>`<li>${esc(a)}</li>`).join('')}</ul><p class="sub">${g.simulated?'此文件为模拟数据，以下规律不能外推到真实平台。':'以下均为当前样本的相关特征，不代表因果或流量保证。'}</p></article>
    <div class="insight-grid" style="margin-top:20px">${evidenceTable('常见标题 Hook',g.hooks)}${evidenceTable('正文结构特征',g.structures)}${evidenceTable('常见场景',g.scenes.filter(s=>s.count).slice(0,5))}${evidenceTable('常用标签',g.tags)}</div>
    <article class="panel" style="margin-top:20px"><h2>本次实际采用的证据 · ${g.references.length} 篇</h2><p class="sub">优先主题相似度，再比较 ViralScore，并减少同作者与高度重复正文；以下原文用于生成和 Critic 复核。词组相似不是语义相似概率。规律频次来自整个同类组。</p>${g.references.map(n=>`<div class="feature"><button class="note-title" data-note="${esc(n.id)}">${esc(n.title)}</button><p class="sub">${esc(n.id)} · ViralScore ${n.score.toFixed(3)}</p><p class="sub">${(n.match_reasons||[]).map(esc).join('；')}</p><details><summary>查看采用的原文</summary><div class="original">${esc(n.content)}</div></details></div>`).join('')}</article>
    ${g.semantic?`<article class="panel" style="margin-top:20px"><h2>LLM 可迁移规律</h2><p class="sub">同类子样本 ${g.semantic.sample_count}/${g.semantic.population} 篇；Lift 不外推全量，不代表因果。</p>${g.semantic.rows.map(r=>`<div class="feature"><h3>${esc(r.name)}</h3><p>${associationHtml(r)}</p><p class="sub">${r.count}/${r.total} 与 ${r.other_count}/${r.other_total}</p>${r.examples.map(e=>`<div class="evidence">${esc(e.quote)}<br><span class="sub">${esc(e.id)} · ${esc(e.reason||'')}</span></div>`).join('')}</div>`).join('')}</article>`:''}</section><section data-generator-section="3" ${generatorStep===3?'':'hidden'}><h2 style="margin-top:26px">新的内容方案</h2><p class="sub">${esc(g.mode)}。包含待补充信息的可编辑草稿，发布前核实事实。</p>
    ${g.plans.map((p,i)=>`<article class="idea"><span class="badge">方案 ${i+1} · ${esc(p.angle)}</span><h2 style="margin-top:10px">${esc(p.topic)}</h2><h3>01 选题策略</h3><p><strong>目标：</strong>${esc(p.strategy?.objective||p.angle)}</p><p><strong>面向：</strong>${esc(p.strategy?.audience||g.audience)}</p><p>${esc(p.strategy?.thesis||p.basis)}</p><p class="sub">依据：${esc(p.strategy?.evidence||p.basis)}</p><h3>02 标题 A / B / C</h3>${p.titles.map((t,j)=>`<div class="evidence"><strong>${['A','B','C'][j]}</strong>　${esc(t)}</div>`).join('')}<h3>03 完整笔记</h3><p class="sub">场景：${esc(p.scene)} · 结构：${esc(p.outline.join(' → '))}</p><label>笔记正文（可编辑）<textarea data-draft="${i}" style="min-height:270px">${esc(p.body)}</textarea></label><p class="sub">配图建议：${esc(p.visuals.join('；'))}</p><p class="sub">依据：${esc(p.basis)} 参考 ${p.reference_ids.map(esc).join('、')}</p><p class="sub">${esc(p.validation)}</p><button data-copy-draft="${i}">复制标题与正文</button></article>`).join('')}
    </section><section data-generator-section="4" ${generatorStep===4?'':'hidden'}>${assessmentView(g)}</section>`;
}

async function runGenerator(){
    if($('#full-agent')?.checked)return runFullPipeline();
    saveBrief();sessionStorage.setItem('facts',$('#facts').value);sessionStorage.setItem('generator-category',$('#generator-category').value);
    const request={facts:$('#facts').value,topic:$('#product').value.trim(),audience:$('#audience').value,brief:$('#brief').value,category:$('#generator-category').value,simulated:dataset.simulated,
        analysis:{sheets:dataset.sheets.filter(s=>selectedSheets.includes(s.name)),mapping:dataset.mapping,weights,filters,as_of:result.as_of,top_pct:result.top_pct}};
    // Freeze the evidence scope for the later explicit AI action.
    const snapshot=JSON.parse(JSON.stringify(request));
    if($('#pipeline-progress'))$('#pipeline-progress').textContent='Generate：检索相似证据并生成三套方案 → Critic：自动评分与自检 → Refine：尝试优化并复评…';
    const response=await api('generator',snapshot);
    generatorRequest=snapshot;generatorResult=response;generatorStep=response.status==='ready'?3:2;render();
}

function bindGenerator(){
    document.querySelectorAll('[data-generator-step]').forEach(b=>b.onclick=()=>{if(b.disabled)return;if(generatorStep===1){saveBrief();if($('#facts'))sessionStorage.setItem('facts',$('#facts').value);if($('#generator-category'))sessionStorage.setItem('generator-category',$('#generator-category').value)}generatorStep=Number(b.dataset.generatorStep);render()});
    bindAssessment();
    const bind=(id,fn)=>{const el=$('#'+id);if(el)el.onclick=()=>withButton(el,fn)};
    bind('generator-export',()=>download('Content-Generator-方案.json',JSON.stringify(generatorResult,null,2)));
    document.querySelectorAll('[data-draft]').forEach(el=>el.oninput=()=>{if(agentBusy){el.value=generatorResult.plans[Number(el.dataset.draft)].body;return}generatorResult.plans[Number(el.dataset.draft)].body=el.value;generatorResult.assessment=null;if($('#assessment')){$('#assessment').outerHTML=assessmentView(generatorResult);bindAssessment()}});
    document.querySelectorAll('[data-copy-draft]').forEach(el=>el.onclick=()=>withButton(el,async()=>{
        const p=generatorResult.plans[Number(el.dataset.copyDraft)];await navigator.clipboard.writeText(p.titles[0]+'\n\n'+p.body);toast('已复制标题与正文');
    }));
}
