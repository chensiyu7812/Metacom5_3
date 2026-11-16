const meta=JSON.parse(document.getElementById('delta-meta').textContent);
const key=meta.version;
let imported=null,started=new Date().toISOString();
function validateImport(d){
 if(![meta.version,meta.previous_version].includes(d.version)||d.proposal_identity!==meta.proposal_identity||!Array.isArray(d.answers))throw Error('文件版本或研究身份不匹配。');
 const seen=new Set();
 for(const a of d.answers){
  const b=meta.all_bindings.find(x=>x.pair_id===a.pair_id);
  if(!b||seen.has(a.pair_id)||a.left_reply_identity!==b.left_reply_identity||a.right_reply_identity!==b.right_reply_identity)throw Error('回复绑定不匹配或存在重复题号。');
  if(a.direction!==null&&!['A','B','tie','unknown'].includes(a.direction))throw Error('判断字段不合法。');
  if(a.reason!==undefined&&typeof a.reason!=='string')throw Error('理由字段不合法。');
  seen.add(a.pair_id);
 }
 return d;
}
function data(){return {version:meta.version,proposal_identity:meta.proposal_identity,started,exported:new Date().toISOString(),
 reference_scope:'7 missing pairs; historical P04 separately reused, no new rating inferred',
 new_scores_seen:document.getElementById('seen').value||null,self_reported_minutes:document.getElementById('minutes').value||null,
 answers:[...document.querySelectorAll('section[data-pair]')].map(s=>({
  ...meta.all_bindings.find(x=>x.pair_id===s.dataset.pair),
  direction:s.querySelector('input:checked')?.value||null,reason:s.querySelector('textarea').value})),
 imported_original_export:imported,old_exposure_disclosed:true,qualifies_reward:false};}
function restore(d){
 for(const s of document.querySelectorAll('section[data-pair]')){
  const a=d.answers.find(x=>x.pair_id===s.dataset.pair);if(!a)continue;
  for(const e of s.querySelectorAll('input[type=radio]'))e.checked=e.value===a.direction;
  s.querySelector('textarea').value=a.reason||'';
  if(a.uncertainty)s.querySelector('textarea').value+='\n原作答中的未决说明：'+a.uncertainty;
 }
 document.getElementById('seen').value=d.new_scores_seen||'';
 document.getElementById('minutes').value=d.self_reported_minutes||'';
 started=d.started||started;
}
function save(){
 const d=data(),n=d.answers.filter(x=>x.direction!==null).length;
 let saved=true;try{localStorage.setItem(key,JSON.stringify(d));}catch(e){saved=false;}
 document.getElementById('progress').textContent=`已选择 ${n}/7 组；第4组已引用旧记录，无需重填。${saved?'草稿已保存到本机浏览器。':'浏览器未能保存，请下载JSON保留。'}`;
}
try{const old=JSON.parse(localStorage.getItem(key)||'null');if(old){validateImport(old);restore(old);imported=old.imported_original_export||null;}}catch(e){document.getElementById('notice').textContent='旧草稿未恢复；可导入你此前下载的JSON，不会自动补答案。';}
document.addEventListener('input',save);document.addEventListener('change',save);
document.getElementById('download').onclick=()=>{
 const blob=new Blob([JSON.stringify(data(),null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');
 a.href=url;a.download='PMRL1_delta_7pairs_'+new Date().toISOString().replaceAll(':','-')+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};
document.getElementById('import').onchange=async e=>{
 try{const f=e.target.files[0];if(!f)return;const d=validateImport(JSON.parse(await f.text()));restore(d);imported=d;save();document.getElementById('notice').textContent='已恢复你文件中的实际答案；原导出完整保留在新导出的 imported_original_export 中，包括已移除的第4组。';}
 catch(e){document.getElementById('notice').textContent='没有导入：'+e.message;}
};
for(const search of document.querySelectorAll('input[data-search]'))search.oninput=()=>{
 const root=document.getElementById(search.dataset.search),term=search.value.trim().toLowerCase();
 for(const t of root.querySelectorAll('.turn'))t.hidden=!!term&&!t.textContent.toLowerCase().includes(term);
 for(const h of root.querySelectorAll('details.history')){h.hidden=![...h.querySelectorAll('.turn')].some(t=>!t.hidden);if(term&&!h.hidden)h.open=true;}
};
save();
