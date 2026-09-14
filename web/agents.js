let semanticState=null;
let agentBusy=false;
function diagnosticsView(){return `<article class="panel" style="margin-top:22px"><h2>ViralScore · 分布与敏感性检查</h2><p class="sub">查看互动数据分位数，并检查移除单个维度后，高表现组会变化多少。当前数据没有独立层级标签，因此不把前 20% 当作正确答案。</p><button id="diagnostics-run">检查当前评分范围</button><div id="diagnostics-result"></div></article>`}
function bindDiagnostics(){const button=$('#diagnostics-run');if(!button)return;button.onclick=()=>withButton(button,async()=>{const out=await api('diagnostics',{sheets:dataset.sheets.filter(s=>selectedSheets.includes(s.name)),mapping:dataset.mapping,weights,filters,as_of:result.as_of,top_pct:result.top_pct});$('#diagnostics-result').innerHTML=`<div class="table-wrap" style="margin-top:15px"><table><thead><tr><th>指标</th><th>P10</th><th>中位数</th><th>P90</th><th>P99</th><th>最大值</th></tr></thead><tbody>${Object.entries(out.distribution).map(([key,v])=>`<tr><td>${esc(labels[key]||key)}</td>${['p10','median','p90','p99','maximum'].map(k=>`<td>${fmt(v[k])}</td>`).join('')}</tr>`).join('')}</tbody></table></div><h3 style="margin-top:20px">去掉单个维度后的高表现组保留率</h3>${out.sensitivity.map(s=>`<p class="sub">移除 ${esc(labels[s.excluded])}：保留 ${s.retained}/${s.baseline} 篇（${fmt(s.retention_pct)}%）</p>`).join('')||'<p class="sub">当前有效维度或样本不足，无法进行移除比较。</p>'}<p class="tip">${esc(out.note)}</p>`})}
function setAgentBusy(value){agentBusy=value;document.body.classList.toggle('agent-running',value)}
function associationHtml(row){return `Lift ${row.lift==null?'—':row.lift.toFixed(2)} · ${esc(row.association||'无法判断')} · 比例差 ${row.difference_pp==null?'—':row.difference_pp.toFixed(1)+' 个百分点'}`}
function associationStats(a,h,b,o){const lift=h&&o&&a+b?(a/(a+b))/(h/(h+o)):null;return {lift,difference_pp:h&&o?a/h*100-b/o*100:null,association:lift==null?'无法判断':lift>1+1e-9?'正关联':lift<1-1e-9?'负关联':'无差异'}}
function semanticRows(notes,annotations){
 const lookup=new Map(notes.map(n=>[n.id,n]));const names=Object.keys(annotations[0]?.features||{});
 return names.map(name=>{let a=0,h=0,b=0,o=0;const examples=[];for(const item of annotations){const n=lookup.get(item.id),f=item.features[name];if(!n||f.present==null)continue;if(n.high){h++;a+=Number(f.present)}else{o++;b+=Number(f.present)}if(f.present&&examples.length<3)examples.push({id:item.id,quote:f.quote,reason:f.reason})}return {name,count:a,total:h,other_count:b,other_total:o,examples,...associationStats(a,h,b,o)}});
}
function sampleNotes(notes,limit){
 const high=notes.filter(n=>n.high&&n.score!=null),other=notes.filter(n=>!n.high&&n.score!=null);
 const pick=(arr,n)=>{arr=[...arr].sort((a,b)=>a.id.localeCompare(b.id));return Array.from({length:Math.min(n,arr.length)},(_,i)=>arr[Math.floor(i*arr.length/Math.min(n,arr.length))])};
 if(notes.length<=limit)return notes.filter(n=>n.score!=null);
 const h=Math.min(high.length,Math.max(1,Math.round(limit*high.length/Math.max(1,high.length+other.length))));
 return [...pick(high,h),...pick(other,limit-h)];
}
function semanticView(){return `<article class="panel" style="margin-top:22px"><h2>LLM 语义规律分析</h2><p class="sub">模型逐篇判断含义并引用原文，后端核对证据；统计由程序计算，模型不直接填写 Lift。模型标注时看不到分数和分组。</p><div class="toolbar"><label>分析范围 <select id="semantic-limit"><option value="40">最多 40 篇分层子样本</option><option value="100">最多 100 篇分层子样本</option><option value="10000">当前全部可评分笔记</option></select></label><button class="primary" id="semantic-run" ${status.connected?'':'disabled'}>发送所选样本，运行语义分析</button><button id="semantic-stop" disabled>停止后续批次</button></div><p class="ai-note">将发送所选笔记的 ID、标题、正文，每批最多 8 篇；模型调用可能产生费用。${status.connected?'':'AI 未连接，语义功能不可用。'}</p><p class="tip">Lift = P(高表现 | 特征出现) / P(高表现)，基于当前已分析样本。大于 1 为正关联，小于 1 为负关联；不代表因果或统计显著。证据不足项不计入分母。</p><div id="semantic-progress" role="status"></div><div id="semantic-results">${semanticState?semanticOutput(semanticState):''}</div></article>`}
function semanticOutput(s){return `<p class="sub">${s.complete?'已完成':'部分结果'}：成功标注 ${s.annotations.length}/${s.notes.length} 篇；当前范围 ${s.population} 篇。${s.notes.length<s.population?'这是分层子样本，不能视为全量统计。':''}</p><div class="insight-grid">${s.rows.map(r=>`<div class="panel"><h3>${esc(r.name)}</h3><p class="badge gray">${associationHtml(r)}</p><p class="sub">高表现 ${r.count}/${r.total} · 其余 ${r.other_count}/${r.other_total}</p>${r.examples.map(e=>`<div class="evidence">${esc(e.quote)}<br><span class="sub">${esc(e.id)} · ${esc(e.reason)}</span></div>`).join('')}</div>`).join('')}</div>`}
function bindSemantic(){
 bindPatternCategory();
 const button=$('#semantic-run');if(!button)return;
 let stopped=false;$('#semantic-stop').onclick=()=>{stopped=true;$('#semantic-progress').textContent='已请求停止；当前请求结束后不再发送下一批。'};
 button.onclick=()=>withButton(button,async()=>{
  if(agentBusy)throw Error('另一项 Agent 任务正在运行。');setAgentBusy(true);stopped=false;
  const snapshot=JSON.parse(JSON.stringify((patternResult||result).notes.filter(n=>n.score!=null)));const selected=sampleNotes(snapshot,Number($('#semantic-limit').value));
  const state={notes:selected,annotations:[],rows:[],population:snapshot.length,complete:false};semanticState=state;$('#semantic-stop').disabled=false;
  try{if(!selected.length)throw Error('当前没有可评分笔记。');for(let i=0;i<selected.length&&!stopped;i+=8){$('#semantic-progress').textContent=`正在分析第 ${i+1}–${Math.min(i+8,selected.length)} 篇，共 ${selected.length} 篇…`;const out=await api('semantic',{notes:selected.slice(i,i+8)});state.annotations.push(...out.notes);state.rows=semanticRows(state.notes,state.annotations);if($('#semantic-results'))$('#semantic-results').innerHTML=semanticOutput(state)}state.complete=state.annotations.length===selected.length;if($('#semantic-results'))$('#semantic-results').innerHTML=semanticOutput(state);if($('#semantic-progress'))$('#semantic-progress').textContent=state.complete?'语义分析完成。':'已停止，保留并标注部分结果。'}catch(e){if($('#semantic-progress'))$('#semantic-progress').textContent='未完成：'+e.message+'；已完成批次保留为部分结果。';throw e}finally{setAgentBusy(false);if($('#semantic-stop'))$('#semantic-stop').disabled=true}
 });
}

function reviewContext(g){return {topic:g.topic,brief:g.brief,audience:g.audience,facts:g.facts||'',references:g.references,simulated:g.simulated}}
function bestIndex(evals){return evals.reduce((best,e,i)=>e.blockers.length<evals[best].blockers.length||e.blockers.length===evals[best].blockers.length&&e.score>evals[best].score?i:best,0)}
function criticWinnerReason(evals,best){const e=evals[best],others=evals.filter((_,i)=>i!==best),gains=Object.entries(e.dimensions).map(([k,v])=>[v-others.reduce((s,x)=>s+x.dimensions[k],0)/Math.max(1,others.length),k]).filter(x=>x[0]>0).sort((a,b)=>b[0]-a[0]).slice(0,2).map(x=>x[1]);return `方案 ${best+1} 胜出：${gains.join('、')||'阻碍项更少'}更强；质量分 ${e.score}，待处理阻碍项 ${e.blockers.length} 个。`}
function assessmentView(g){const a=g.assessment;return `<article class="panel" id="assessment" style="margin-top:22px"><h2>Critic Agent · Generate → Evaluate → Refine</h2><p class="sub">独立六维量表：需求匹配 20、标题吸引力 20、事实完整度 20、结构清晰度 15、原创度 15、参考过度相似风险 10。优先比较阻碍项，再比较总分。</p><div class="toolbar"><button id="review-all">${a?'重新评估当前三套方案':'评估当前三套方案'}</button><span class="sub">${g.review_ai?'使用 LLM 评估，将发送当前草稿、简报、事实和参考原文。':'本地规则根据每套方案自身标题、结构、事实和相似度分别评分。'}</span></div>${a?`<p class="score-summary">${esc(a.winner_reason||criticWinnerReason(a.evaluations,a.best_index))}</p><div class="insight-grid">${a.evaluations.map((e,i)=>`<article class="panel"><span class="badge ${a.best_index===i?'':'gray'}">方案 ${i+1}${a.best_index===i?' · 当前选择':''}</span><h3 style="margin-top:12px">质量分 ${fmt(e.score)} / 100</h3><p class="sub">${esc(e.mode)}</p><p class="sub">${Object.entries(e.dimensions).map(([k,v])=>`${esc(k)} ${v}`).join(' · ')}</p><p>${esc(e.rationale)}</p><ul>${e.issues.map(s=>`<li>${esc(s)}</li>`).join('')}</ul><p class="tip">待处理：${e.blockers.map(esc).join('；')||'未发现规则内阻碍项，仍需人工核实事实'}</p><button data-select-plan="${i}">选用这套方案</button></article>`).join('')}</div><div class="ai-actions"><button class="primary" id="optimize-best">根据建议自动优化当前方案</button><span class="sub">优化后重新评分；若变差则保留原稿。</span></div><div id="review-progress" role="status"></div><h3>最终笔记 · 方案 ${a.best_index+1}</h3><p class="sub">建议稿，发布前核实产品事实。修改上方正文后需重新评估。</p><div class="ai-output">${esc(a.final.titles[0])}\n\n${esc(a.final.body)}</div><button id="copy-final" style="margin-top:12px">复制最终笔记</button>${a.history?.length?`<details style="margin-top:15px"><summary>优化前后差异（${a.history.length} 轮）</summary>${a.history.map(h=>`<div class="feature"><p>方案 ${h.index+1}：${h.result.before.score} → ${h.result.after.score} · ${esc(h.result.reason)}</p><ul>${h.result.changes.map(c=>`<li>${esc(c)}</li>`).join('')||'<li>本轮没有产生可验证改动</li>'}</ul><details><summary>查看优化前后正文</summary><pre>${esc(h.before.body)}</pre><pre>${esc(h.result.candidate.body)}</pre></details></div>`).join('')}</details>`:''}`:'<p class="tip">草稿已修改或尚未评估，原评分与最终稿已失效。请重新评估。</p>'}</article>`}
async function performReviews(g,useAI,progress=()=>{}){
 const evaluations=[];for(let i=0;i<g.plans.length;i++){progress(`内容评分 Agent 正在评估方案 ${i+1}/3…`);evaluations.push(await api('review',{plan:g.plans[i],context:reviewContext(g),use_ai:useAI}))}
 const best=bestIndex(evaluations);g.assessment={evaluations,best_index:best,winner_reason:criticWinnerReason(evaluations,best),final:JSON.parse(JSON.stringify(g.plans[best])),history:[]};g.review_ai=useAI;
}
function bindAssessment(){
 const g=generatorResult;if(!g||g.status!=='ready')return;
 const action=(id,fn)=>{const el=$('#'+id);if(el)el.onclick=()=>withButton(el,async()=>{if(agentBusy)throw Error('Agent 正在运行，请等待完成。');setAgentBusy(true);try{await fn()}finally{setAgentBusy(false)}})};
 action('review-all',async()=>{const stamp=JSON.stringify(g.plans);await performReviews(g,Boolean(g.review_ai),s=>{if($('#review-progress'))$('#review-progress').textContent=s});if(stamp!==JSON.stringify(g.plans)){g.assessment=null;throw Error('评估期间草稿已变动，请重新评估。')}render()});
 document.querySelectorAll('[data-select-plan]').forEach(b=>b.onclick=()=>{if(agentBusy)return;const i=Number(b.dataset.selectPlan);g.assessment.best_index=i;g.assessment.winner_reason=`用户手动选择方案 ${i+1}；请结合六维分数和产品事实复核。`;g.assessment.final=JSON.parse(JSON.stringify(g.plans[i]));render()});
 action('optimize-best',async()=>{const i=g.assessment.best_index,before=JSON.parse(JSON.stringify(g.plans[i]));$('#review-progress').textContent='Critic 正在按建议优化，并重新评估；可能需要多个模型请求…';const out=await api('optimize',{plan:before,context:reviewContext(g),use_ai:Boolean(g.review_ai)});if(JSON.stringify(before)!==JSON.stringify(g.plans[i])||!g.assessment)throw Error('优化期间草稿已修改，请重新评估。');g.assessment.history.push({index:i,before,result:out});g.plans[i]=out.final;g.assessment.evaluations[i]=out.accepted?out.after:out.before;g.assessment.final=out.final;g.assessment.winner_reason=criticWinnerReason(g.assessment.evaluations,g.assessment.best_index);render()});
 action('copy-final',async()=>{await navigator.clipboard.writeText(g.assessment.final.titles[0]+'\n\n'+g.assessment.final.body);toast('已复制最终笔记')});
}

async function runFullPipeline(){
 if(agentBusy)throw Error('另一项 Agent 任务正在运行。');setAgentBusy(true);
 const progress=s=>{if($('#pipeline-progress'))$('#pipeline-progress').textContent=s};
 saveBrief();const request={topic:$('#product').value.trim(),audience:$('#audience').value,brief:$('#brief').value,facts:$('#facts').value,category:$('#generator-category').value,simulated:dataset.simulated,analysis:{sheets:dataset.sheets.filter(s=>selectedSheets.includes(s.name)),mapping:dataset.mapping,weights,filters,as_of:result.as_of,top_pct:result.top_pct}};
 const auto=$('#auto-optimize').checked;sessionStorage.setItem('facts',request.facts);
 try{
  progress('1/7 意图识别…');const intent=await api('intent',request);
  progress('2/7 检索相似高表现笔记…');const snapshot=JSON.parse(JSON.stringify({...request,prepare_only:true,category:request.category||intent.category}));const g=await api('generator',snapshot);g.intent=intent;
  generatorRequest=snapshot;generatorResult=g;
  if(g.status!=='ready'){render();return}
  progress('3/7 LLM 语义提炼与 Lift 统计…');
  // Same-category controls are included to estimate associations, not only success examples.
  const categoryNotes=result.notes.filter(n=>n.score!=null&&g.matched_ids.includes(n.id));
  const sample=sampleNotes(categoryNotes,24),annotations=[];
  for(let i=0;i<sample.length;i+=8){progress(`3/7 语义分析 ${Math.min(i+8,sample.length)}/${sample.length} 篇…`);const r=await api('semantic',{notes:sample.slice(i,i+8)});annotations.push(...r.notes)}
  g.semantic={rows:semanticRows(sample,annotations),notes:sample.map(n=>({id:n.id,high:n.high})),annotations,sample_count:sample.length,population:categoryNotes.length};
  progress('4/7 生成三套方案…');const drafted=await api('draft',{context:{...reviewContext(g),intent,semantic:g.semantic.rows,semantic_sample_count:sample.length,semantic_population:categoryNotes.length,rule_evidence:{hooks:g.hooks,structures:g.structures,scenes:g.scenes,tags:g.tags}}});g.plans=drafted.plans;g.assessment=null;g.mode='LLM 需求识别、语义分析与内容生成';
  progress('5/7 内容评分 Agent…');await performReviews(g,true,progress);
  if(auto){progress('6/7 根据建议优化最佳方案并复评…');const i=g.assessment.best_index,before=JSON.parse(JSON.stringify(g.plans[i]));const out=await api('optimize',{plan:before,context:reviewContext(g),use_ai:true});g.assessment.history.push({index:i,before,result:out});g.plans[i]=out.final;g.assessment.evaluations[i]=out.accepted?out.after:out.before;g.assessment.best_index=bestIndex(g.assessment.evaluations);g.assessment.final=JSON.parse(JSON.stringify(g.plans[g.assessment.best_index]))}
  progress('7/7 已形成最终建议稿');generatorStep=4;render();
 }catch(e){if(generatorResult?.status==='ready'){generatorResult.pipeline_error=e.message;render()}progress('流程未完成：'+e.message+'。已完成结果保留；可重新运行或评估。');throw e}finally{setAgentBusy(false)}
}
