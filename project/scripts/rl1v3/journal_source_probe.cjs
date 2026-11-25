// Reproduce the web-side development data probe on locally held sources.
// Run: node journal_source_probe.cjs evo_emo.json sanitized_runtime.json qa_identity.jsonl AnnoMI-full.csv > result.json
// No generation, model loading, network or raw text export. Keep source data local.
function probe(rawText,sanitizedText,identityText,annoText){
  const count=(xs,f)=>{const m={};for(const x of xs){let k=f(x);m[k]=(m[k]||0)+1}return m};
  function parseCSV(s){let rows=[],row=[],v="",quoted=false;for(let i=0;i<s.length;i++){let x=s[i];if(quoted){if(x==='"'){if(s[i+1]==='"'){v+='"';i++}else quoted=false}else v+=x}else if(x==='"')quoted=true;else if(x===','){row.push(v);v=""}else if(x==='\n'){row.push(v.replace(/\r$/,""));if(row.some(Boolean))rows.push(row);row=[];v=""}else v+=x}if(row.length||v){row.push(v.replace(/\r$/,""));rows.push(row)}if(quoted)throw Error("unclosed CSV");let h=rows.shift();if(rows.some(x=>x.length!==h.length))throw Error("ragged CSV");return rows.map(x=>Object.fromEntries(h.map((k,i)=>[k,x[i]])))}
  const words=s=>new Set((s.toLowerCase().match(/[a-z0-9']+/g)||[]));
  const intersection=(a,b)=>{let n=0;for(const w of a)if(b.has(w))n++;return n};
  // Same ASCII term-overlap formula as retrieve/v0.py, applied to a QA query and
  // RAW session instead of the production last-three-turn prefix. Not production execution.
  const score=(a,b)=>intersection(a,b)/Math.max(1,a.size);
  const raw=JSON.parse(rawText),san=JSON.parse(sanitizedText).users,qa=identityText.trim().split("\n").map(JSON.parse),rows=parseCSV(annoText);
  if(raw.length!==san.length)throw Error("owner mismatch");
  let pastSeeker=0,legalSeekerNext=0,allSeekerNext=0,sharedSession=new Map;
  for(const u of san){const minRank=Math.min(...u.sessions.map(s=>s.chronological_rank));for(const s of u.sessions){
    if(!sharedSession.has(s.session_id))sharedSession.set(s.session_id,new Set);sharedSession.get(s.session_id).add(u.owner_id);
    for(let i=0;i<s.turns.length;i++)if(s.turns[i].role==="seeker"){if(s.chronological_rank>minRank)pastSeeker++;if(s.turns[i+1]?.role==="supporter"){allSeekerNext++;if(s.chronological_rank>minRank)legalSeekerNext++}}}}
  const resolution={questions:0,emptyEvidence:0,allResolved:0,partiallyResolved:0,noneResolved:0,exactTurnRefs:0,eventToSessionRefs:0,directSessionRefs:0,unresolvedRefs:0,duplicateEvidenceRefs:0,fullHistoryResolvableWithEvidence:0,multiSessionResolved:0,groupSessionQuestions:0,strictPriorAll:0,hasSameOrLater:0,groupNoRankOrUnresolved:0};
  const ret={denominator:0,top1Any:0,top2Any:0,top4Any:0,top1All:0,top2All:0,top4All:0,recency1Any:0,recency4All:0};
  let byCapability={};
  for(const u of raw){let sessions=u.dialog_history, byId=new Map(sessions.map(s=>[s.id,s])),events=new Map(u.event_experience.map(e=>[e.id,e])), sUser=san.find(x=>x.owner_id===u.id);
    if(!sUser)throw Error("sanitized owner not found");
    let rank=new Map(sUser.sessions.map(s=>[s.session_id,s.chronological_rank]));
    let docs=sessions.map(s=>({id:s.id,rank:rank.get(s.id),terms:words(s.dialogue.map(t=>t.content).join("\n"))}));
    function resolve(e){if(byId.has(e))return [e,"directSessionRefs"];if(events.has(e)){let c=events.get(e).conv_id;return byId.has(c)?[c,"eventToSessionRefs"]:[null,"unresolvedRefs"]}let k=e.lastIndexOf(":");if(k>0){let id=e.slice(0,k),idx=e.slice(k+1);if(byId.has(id)&&byId.get(id).dialogue.some(t=>String(t.idx)===idx))return [id,"exactTurnRefs"]}return [null,"unresolvedRefs"]}
    for(const g of u.questions)for(const q of g.questions){resolution.questions++;let ev=q.evidence||[];resolution.duplicateEvidenceRefs+=ev.length-new Set(ev).size;if(!ev.length){resolution.emptyEvidence++;continue}
      let gs=new Set,missing=0;for(const e of ev){let [id,type]=resolve(e);resolution[type]++;if(id)gs.add(id);else missing++}
      if(missing===ev.length)resolution.noneResolved++;else if(missing)resolution.partiallyResolved++;else resolution.allResolved++;
      if(rank.has(g.id)){resolution.groupSessionQuestions++;if(!missing){if([...gs].every(id=>rank.get(id)<rank.get(g.id)))resolution.strictPriorAll++;else resolution.hasSameOrLater++}else resolution.groupNoRankOrUnresolved++}else resolution.groupNoRankOrUnresolved++;
      if(missing||!gs.size)continue;
      resolution.fullHistoryResolvableWithEvidence++;if(gs.size>1)resolution.multiSessionResolved++;
      const query=words(q.question), ranked=docs.slice().sort((a,b)=>score(query,b.terms)-score(query,a.terms)||b.rank-a.rank||a.id.localeCompare(b.id)),recent=docs.slice().sort((a,b)=>b.rank-a.rank||a.id.localeCompare(b.id));
      function hit(list,k,all){let ids=new Set(list.slice(0,k).map(x=>x.id));return all?[...gs].every(id=>ids.has(id)):[...gs].some(id=>ids.has(id))}
      ret.denominator++;for(const k of [1,2,4]){ret["top"+k+"Any"]+=+hit(ranked,k,false);ret["top"+k+"All"]+=+hit(ranked,k,true)}ret.recency1Any+=+hit(recent,1,false);ret.recency4All+=+hit(recent,4,true);
      const p=byCapability[q.capability]??(byCapability[q.capability]={n:0,top1Any:0,top4All:0});p.n++;p.top1Any+=+hit(ranked,1,false);p.top4All+=+hit(ranked,4,true);
    }
  }
  const groups=new Map;for(const x of rows){if(!groups.has(x.transcript_id))groups.set(x.transcript_id,[]);groups.get(x.transcript_id).push(x)}for(const xs of groups.values())xs.sort((x,y)=>+x.utterance_id-+y.utterance_id);
  const family=u=>u.trim().replace(/^https?:\/\/(www\.)?/,"").replace(/#.*$/,"").replace(/&(?:t|start)=.*$/,"");
  const contexts=[];for(const xs of groups.values()){for(let i=1;i<xs.length;i++){const x=xs[i];if(x.interlocutor!=="therapist"||xs[i-1].interlocutor!=="client")continue;let prev=xs.slice(0,i).filter(z=>z.interlocutor==="client").slice(-3);contexts.push({family:family(x.video_url),transcript:x.transcript_id,quality:x.mi_quality,y:x.main_therapist_behaviour,ctx:prev.map(z=>z.utterance_text).join(" "),lastThree:xs.slice(Math.max(0,i-3),i).map(z=>z.utterance_text).join("\n"),response:x.utterance_text,talk:prev.map(z=>z.client_talk_type)})}}
  function hash(s){let h=2166136261;for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619)}return h>>>0}
  const train=contexts.filter(x=>hash(x.family)%5!==0),test=contexts.filter(x=>hash(x.family)%5===0),majority=Object.entries(count(train,x=>x.y)).sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0]))[0][0];
  const stop=new Set("a an the of and or but i you he she it we they is are was were be been being to for in on that this those these at as with have has had my your their me him her us them do does did so if can could would should just really like know yeah yes no not".split(" "));
  const cosineWords=s=>new Set((s.toLowerCase().match(/[a-z]+/g)||[]).filter(x=>x.length>2&&!stop.has(x)));
  function knn(mode){const isCos=mode==="client_context_cosine",term=isCos?cosineWords:words;
    const docs=train.map((x,i)=>({i,terms:term(isCos?x.ctx:mode==="legacy_case_overlap"?x.lastThree+"\n"+x.response:x.lastThree)}));
    let inv=new Map;for(const d of docs)for(const w of d.terms){if(!inv.has(w))inv.set(w,[]);inv.get(w).push(d.i)}
    let correct=0,zero=0,byClass={};
    for(const x of test){let ws=term(isCos?x.ctx:x.lastThree),hits=new Map;for(const w of ws)for(const i of inv.get(w)||[])hits.set(i,(hits.get(i)||0)+1);
      let best=-1,bs=0;for(const [i,n] of hits){let z=isCos?n/Math.sqrt(ws.size*docs[i].terms.size):n/Math.max(1,ws.size);if(z>bs||z===bs&&i<best){best=i;bs=z}}
      if(best<0)zero++;const p=best<0?majority:train[best].y;correct+=+(p===x.y);const v=byClass[x.y]??(byClass[x.y]={n:0,correct:0});v.n++;v.correct+=+(p===x.y)}
    return {correct,n:test.length,accuracy:correct/test.length,balancedAccuracy:Object.values(byClass).reduce((s,x)=>s+x.correct/x.n,0)/Object.keys(byClass).length,zeroOverlap:zero,byClass}
  }
  let th=rows.filter(x=>x.interlocutor==="therapist");
  return {evidence_level:"actual_data_development_probe_not_generator_or_policy_efficacy",evo:{owners:san.length,sessions:san.reduce((n,u)=>n+u.sessions.length,0),roles:count(san.flatMap(u=>u.sessions.flatMap(s=>s.turns)),t=>t.role),pastSeeker,allSeekerNext,legalSeekerNext,sharedSessionIDs:[...sharedSession.values()].filter(x=>x.size>1).length,qa:{n:qa.length,groups:new Set(qa.map(x=>x.owner_id+"|"+x.question_group_id)).size,uniqueQuestionHashes:new Set(qa.map(x=>x.question_normalized_sha256)).size,byCapability:count(qa,x=>x.capability),byEvidenceCount:count(qa,x=>x.evidence_count)},resolution,fullHistoryLexicalDiagnostic:ret,byCapability},annomi:{rows:rows.length,transcripts:groups.size,videoFamilies:new Set(rows.map(x=>family(x.video_url))).size,quality:count([...groups.values()],x=>x[0].mi_quality),roles:count(rows,x=>x.interlocutor),main:count(th,x=>x.main_therapist_behaviour),reflection:count(th,x=>x.reflection_subtype),question:count(th,x=>x.question_subtype),input:count(th,x=>x.therapist_input_subtype),eligibleContexts:contexts.length,highContexts:contexts.filter(x=>x.quality==="high").length,priorChangeAndSustainProxy:contexts.filter(x=>x.talk.includes("change")&&x.talk.includes("sustain")).length,split:{rule:"FNV-1a(normalized video URL) modulo 5 = 0 is test; development diagnostic, not a preregistered final split",train:train.length,test:test.length,trainFamilies:new Set(train.map(x=>x.family)).size,testFamilies:new Set(test.map(x=>x.family)).size,overlap:[...new Set(train.map(x=>x.family))].filter(f=>test.some(x=>x.family===f)).length},majority:{label:majority,correct:test.filter(x=>x.y===majority).length,n:test.length},client_context_cosine:knn("client_context_cosine"),legacy_context_overlap:knn("legacy_context_overlap"),legacy_case_overlap:knn("legacy_case_overlap")},limits:["QA source IDs are private evaluation-only; group session does not establish official cutoff; full-history lexical diagnostic is not causal as-of retrieval.","Event ID to source session is coarse, not proof of exact event evidence. Evidence-set all-hit is not proof that all references are necessary.","AnnoMI labels describe observed professional behaviors, not uniquely correct actions or clinical outcomes. Split uses URL groups, not verified independent practitioners. No generator, encoder, judge, policy training or clinical inference."]};
}
module.exports=probe;
if(require.main===module){const fs=require('node:fs');const crypto=require('node:crypto');const paths=process.argv.slice(2);if(paths.length!==4)throw Error('four input files required');const buf=paths.map(p=>fs.readFileSync(p));const blob=x=>crypto.createHash('sha1').update(Buffer.from('blob '+x.length+'\0')).update(x).digest('hex');const hashes=buf.map(blob);const expected=["debae3bb229f56654f13ead9d5d7470c7ece9b11","a726aa5008906db518ee332f63f6db14c3df0a0a","5acb9121bdcd329275a6f6d01db26d7fe185a565","dd8aba7b07953bf6c37c3e6e4771485e62e36b32"];if(hashes.some((x,i)=>x!==expected[i]))throw Error('input Git blob SHA differs: '+JSON.stringify(hashes));const result=probe(...buf.map(b=>b.toString('utf8')));console.log(JSON.stringify({...result,source_git_blobs:Object.fromEntries(['evo','sanitized','qa_identity','annomi'].map((k,i)=>[k,hashes[i]]))},null,2));}
