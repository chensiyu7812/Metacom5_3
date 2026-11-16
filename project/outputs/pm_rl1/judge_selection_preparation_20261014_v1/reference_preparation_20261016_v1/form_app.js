/* Offline eight-item worksheet only. No network, model calls or score calculation. */
function emptyClaim(){return {span:'',claim_type:'',subject:'',time:'',action_result:'',source_ids:'',source_quotes:'',relation:'',search_scope:'',consequence:'',severity:'',reason:''};}
function blankState(packet,slot){return {packet_identity:packet.identity,reviewer_slot:slot,reviewer:{name:'',exposure:'',prior_discussion:'',language_limit:''},items:packet.items.map(x=>({item_id:x.item_id,reply_identity:x.reply_identity,evidence_identity:x.evidence_identity,claim_presence:'',claims:[],current_need:'',contribution:'',omission:'',q_status:'',q_value:'',q_min:'',q_max:'',m_status:'',missing_basis:'',reason:'',current_read:false,history_read:false,done:false}))};}
function validateState(state,packet,slot){
 if(state.packet_identity!==packet.identity||state.reviewer_slot!==slot||!state.reviewer||!Array.isArray(state.items)||state.items.length!==packet.items.length)throw Error('不是这份题卷/评审槽位的答案。');
 for(let i=0;i<packet.items.length;i++){let x=state.items[i],p=packet.items[i];if(x.item_id!==p.item_id||x.reply_identity!==p.reply_identity||x.evidence_identity!==p.evidence_identity||!Array.isArray(x.claims))throw Error('题目、回复或来源绑定不符。');}
 return state;
}
function exportRecord(state,packet,slot,now,id){
 validateState(state,packet,slot);
 return {document_kind:'individual_reference_draft_or_submission',version:'pmrl1-eight-reference-20261016-v1',exported_at:now,submission_id:id,not_an_old_score_replacement:true,independent_human_status:'requires_actual_author_and_exposure_review',state:JSON.parse(JSON.stringify(state))};
}
if(typeof module!=='undefined')module.exports={emptyClaim,blankState,validateState,exportRecord};
if(typeof document!=='undefined'){
 const P=JSON.parse(document.getElementById('packet-data').textContent),slot=document.body.dataset.slot,key='pmrl1.reference.'+P.identity+'.'+slot;
 let S=blankState(P,slot),saveOK=true;
 try{const prior=localStorage.getItem(key);if(prior)S=validateState(JSON.parse(prior),P,slot);}catch(e){document.getElementById('status').textContent='未能读取浏览器草稿：'+e.message+'；请保留已有导出文件。';}
 const $=id=>document.getElementById(id),esc=x=>String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function save(){try{localStorage.setItem(key,JSON.stringify(S));saveOK=true;$('status').textContent='已保存本浏览器草稿；已标完成 '+S.items.filter(x=>x.done).length+'/8。请另行导出保留原始答案。';}catch(e){saveOK=false;$('status').textContent='浏览器无法保存，请立即导出JSON保留答案。';}}
 function field(parent,obj,key,label,options){let l=document.createElement('label');l.textContent=label;let el=document.createElement(options?'select':'textarea');el.dataset.field=key;
  if(options){let opts=[['','— 未填写 —'],...options];for(const [v,t] of opts){let o=document.createElement('option');o.value=v;o.textContent=t;el.appendChild(o);}}
  el.value=obj[key]??'';el.addEventListener('input',()=>{obj[key]=el.value;save();});l.appendChild(el);parent.appendChild(l);return el;
 }
 function check(parent,obj,key,label){let l=document.createElement('label'),e=document.createElement('input');e.type='checkbox';e.checked=obj[key]===true;e.addEventListener('change',()=>{obj[key]=e.checked;save();});l.append(e,document.createTextNode(label));parent.appendChild(l);}
 const meta=$('reviewer');field(meta,S.reviewer,'name','姓名或稳定代号');field(meta,S.reviewer,'exposure','此前是否看过这批案例的模型分数、复核或讨论？',[['yes','看过：本次不能称完全盲评'],['no','未看过'],['uncertain','不能确认']]);field(meta,S.reviewer,'prior_discussion','独立填写前是否与他人讨论过？',[['yes','有'],['no','没有'],['uncertain','不能确认']]);field(meta,S.reviewer,'language_limit','英语阅读或其他限制（没有也请写明）');
 P.items.forEach((item,i)=>{
  let a=S.items[i],context=P.contexts[item.context_id],section=document.createElement('section');section.className='card';section.id=item.item_id;
  section.innerHTML='<h2>'+item.item_id+' / 8</h2><h3>完整英文回复</h3><div class="reply">'+esc(item.reply)+'</div><p>来源组 '+esc(item.context_id)+'；截止日期 '+esc(context.current_date)+'。回复与来源按固定哈希绑定。</p><h3>完整当前对话</h3>'+context.current_prefix.map(t=>'<div class="turn"><b>'+esc(t.id)+' ['+esc(t.role)+']</b> '+esc(t.text)+'</div>').join('')+'<details><summary>展开完整合法历史（'+context.legal_past_sessions.length+'个session）</summary>'+context.legal_past_sessions.map(h=>'<h4>'+esc(h.id)+' · '+esc(h.date)+'</h4>'+h.turns.map(t=>'<div class="turn"><b>'+esc(t.id)+' ['+esc(t.role)+']</b> '+esc(t.text)+'</div>').join('')).join('')+'</details><p><a href="materials/'+esc(item.context_id)+'_complete.txt">另开完整合法来源文本</a></p>';
  const form=document.createElement('div');section.appendChild(form);
  check(form,a,'current_read','已阅读本题完整当前对话');check(form,a,'history_read','已核查完整历史（判断unsupported时须说明检查范围）');
  field(form,a,'claim_presence','是否有具体可核查的断言或事实预设？',[['present','有'],['none','没有；请在理由中说明'],['uncertain','不能确定']]);
  const claims=document.createElement('div');form.appendChild(claims);
  function drawClaims(){claims.replaceChildren();a.claims.forEach((c,k)=>{let d=document.createElement('fieldset'),legend=document.createElement('legend');legend.textContent='主张 '+(k+1);d.appendChild(legend);
   field(d,c,'span','最小完整英文原句/片段（可包含问句或混合句）');field(d,c,'claim_type','主张形式',[['assertion','直接断言'],['presupposition','事实预设'],['tentative','试探/假设'],['non_factual','一般性/非事实内容'],['uncertain','不确定']]);
   field(d,c,'subject','谁说、谁经历、涉及谁？');field(d,c,'time','何时；过去/当前/未确定？');field(d,c,'action_result','行动或结果；计划/尝试/完成/效果/不适用？');field(d,c,'source_ids','来源ID：逐项填写；身份合同可写ROLE');field(d,c,'source_quotes','英文来源原文；区分支持哪一部分，不只写相关主题');
   field(d,c,'relation','证据关系',[['supported','支持'],['contradicted','反驳/矛盾'],['unsupported','完整来源缺乏支持'],['uncertain','无法确定'],['non_factual','不构成可核个人事实']]);field(d,c,'search_scope','检查范围与仍缺的证据');field(d,c,'consequence','若有错误，改变哪项核心理解或哪条建议依据？纠正后需要怎样改变？不是按改字数量定严重度。');
   field(d,c,'severity','按原规则的该主张严重度（可独立未知）',[['0','未确认错误 / 0'],['0.25','局部 / 0.25'],['1','实质 / 1'],['unknown','未知：原规则或证据不足'],['not_applicable','不适用']]);field(d,c,'reason','该主张的判定理由及未决点');claims.appendChild(d);
  });}
  drawClaims();let add=document.createElement('button');add.type='button';add.textContent='添加一条主张（可留空，不强造主张）';add.onclick=()=>{a.claims.push(emptyClaim());drawClaims();save();};form.appendChild(add);
  field(form,a,'current_need','当前用户需要什么？请绑定原句');field(form,a,'contribution','回复具体满足了什么？');field(form,a,'omission','具体遗漏了什么；若无重要遗漏，请说明');
  field(form,a,'q_status','原q规则是否足以给等级？',[['single','可给单一档'],['range','仅能给可接受范围'],['unknown','无法确定'],['rule_insufficient','原规则不足']]);field(form,a,'q_value','若可给单档，填写0–4；否则留空');field(form,a,'q_min','若只能给范围，最低可接受档（0–4）');field(form,a,'q_max','若只能给范围，最高可接受档（0–4）');
  field(form,a,'m_status','整体风险按原规则可判到哪一步？不自动从文字推分',[['0','未检出可确认错误 / 0'],['0.25','局部 / 0.25'],['1','实质 / 1'],['unknown','未知']]);field(form,a,'missing_basis','不足主要来自哪里？',[['none','依据足够'],['evidence','证据不足'],['rule','规则边界不足'],['both','两者都有'],['uncertain','仍不能区分']]);field(form,a,'reason','整体理由、覆盖范围和仍未解决的问题');check(form,a,'done','本人已完成本题当前判断（保留未知也可完成）');
  $('items').appendChild(section);
 });
 $('export').onclick=()=>{save();let now=new Date().toISOString(),id=(typeof crypto!=='undefined'&&crypto.randomUUID)?crypto.randomUUID():now+'-'+Math.random().toString(16).slice(2),record=exportRecord(S,P,slot,now,id),url=URL.createObjectURL(new Blob([JSON.stringify(record,null,2)+'\n'],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='PMRL1_'+slot+'_'+now.replace(/[:.]/g,'-')+'_'+id+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);$('status').textContent='已导出独立版本；旧下载文件请保留。完成标记不等于标签已验收。';};
 $('import').onchange=async e=>{try{let f=e.target.files[0];if(!f)return;let record=JSON.parse(await f.text());validateState(record.state,P,slot);if(!confirm('将用所选文件恢复本浏览器草稿。请先导出当前草稿；原下载文件不会被修改。'))return;localStorage.setItem(key,JSON.stringify(record.state));location.reload();}catch(err){$('status').textContent='未导入：'+err.message;}finally{e.target.value='';}};
}
