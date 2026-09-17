"use strict";
(() => {
  const payload = JSON.parse(document.getElementById("form-data").textContent);
  const sheet = payload.sheet;
  const items = sheet.items;
  const verdicts = new Set(["A_better", "B_better", "equivalent", "uncertain"]);
  const key = `paper1-human-v2:${sheet.rater_id}:${payload.sheet_sha256}`;
  const $ = id => document.getElementById(id);
  const clone = x => JSON.parse(JSON.stringify(x));
  let current = 0;
  let answers = items.map(i => ({presentation_id:i.presentation_id, verdict:null, rationale:null}));
  let dirtySinceExport = false;
  const taskNames = {ESC:"情绪支持对话", QA:"历史问答", Summary:"纵向总结", DG:"新对话回复"};
  const rubrics = {
    ESC:"结合当前用户需求，比较整体适当性、共情与情绪贴合、相关性和帮助、连贯自然，以及是否有伤害性或缺乏依据的陈述。",
    QA:"对照参考答案，比较语义正确性、是否直接回答问题，以及是否添加无依据内容。参考为 unknown 时，恰当表示不知道可以是正确回答。",
    Summary:"对照参考总结，比较所问事件与变化的覆盖、时间和因果连贯性、对参考的忠实程度，以及聚焦和简洁性。",
    DG:"比较历史记忆是否正确、个性化是否相关且不过度侵入、情绪支持是否适当，以及是否与当前对话连贯，避免有害、过时或编造的陈述。"
  };
  function message(text, error=false) { $("message").textContent=text; $("message").classList.toggle("error",error); }
  function stable(x) {
    if (Array.isArray(x)) return "["+x.map(stable).join(",")+"]";
    if (x && typeof x === "object") return "{"+Object.keys(x).sort().map(k=>JSON.stringify(k)+":"+stable(x[k])).join(",")+"}";
    return JSON.stringify(x);
  }
  function withoutRatings(x) {
    const result=clone(x);
    if (!Array.isArray(result.items)) throw Error("答卷缺少题目。");
    for (const item of result.items) {
      if (!Object.hasOwn(item,"verdict") || !Object.hasOwn(item,"rationale")) throw Error("答卷缺少填写字段。");
      item.verdict=null; item.rationale=null;
    }
    return result;
  }
  const originalStructure=stable(withoutRatings(sheet));
  function validAnswers(value) {
    if (!Array.isArray(value) || value.length!==items.length) throw Error("题目数量不符。");
    return value.map((a,n)=>{
      if (!a || a.presentation_id!==items[n].presentation_id ||
          (a.verdict!==null && !verdicts.has(a.verdict)) ||
          (a.rationale!==null && typeof a.rationale!=="string")) throw Error("进度中的题目身份或填写内容不符。");
      return {presentation_id:a.presentation_id,verdict:a.verdict,rationale:a.rationale};
    });
  }
  function isComplete(a) { return verdicts.has(a.verdict) && typeof a.rationale==="string" && a.rationale.trim().length>0; }
  function refreshProgress() {
    const done=answers.filter(isComplete).length;
    $("progress").textContent=`已完成 ${done} / ${items.length}`;
    $("export-complete").disabled=done!==items.length;
    for (let n=0;n<items.length;n++) $("question-select").options[n].textContent=`第 ${n+1} 题${isComplete(answers[n])?" · 已完成":""}`;
  }
  function persist() {
    try {
      localStorage.setItem(key,JSON.stringify({sheet_sha256:payload.sheet_sha256,current,answers}));
      $("save-status").textContent="已保存在当前浏览器；休息前请导出进度备份。";
      $("save-status").classList.remove("error");
    } catch (_) {
      $("save-status").textContent="当前浏览器无法保存本机进度。请及时点击“导出进度”，下次导入恢复。";
      $("save-status").classList.add("error");
    }
  }
  function capture() {
    const selected=document.querySelector('input[name="verdict"]:checked');
    const next={presentation_id:items[current].presentation_id,verdict:selected?selected.value:null,rationale:$("rationale").value||null};
    if (stable(next)!==stable(answers[current])) dirtySinceExport=true;
    answers[current]=next;
    refreshProgress(); persist();
  }
  function addList(id, texts) {
    $(id).replaceChildren();
    for (const text of texts) { const li=document.createElement("li"); li.textContent=text; $(id).append(li); }
  }
  function highlight(el,text,query) {
    el.replaceChildren();
    if (!query) { el.textContent=text; return; }
    const lower=text.toLowerCase(), q=query.toLowerCase(); let start=0, found;
    while ((found=lower.indexOf(q,start))!==-1) {
      el.append(document.createTextNode(text.slice(start,found)));
      const mark=document.createElement("mark"); mark.textContent=text.slice(found,found+query.length); el.append(mark);
      start=found+query.length;
    }
    el.append(document.createTextNode(text.slice(start)));
  }
  function showHistory(query="") {
    $("history-sessions").replaceChildren();
    const item=items[current];
    if (item.task!=="DG") return;
    const view=sheet.reference_catalog[item.reference_id];
    query=query.trim(); let count=0;
    view.sessions.forEach((s,n)=>{
      const raw=`Prior session [${s.timestamp}]:\n`+s.turns.map(t=>`${t.role}: ${t.content}`).join("\n");
      if (query && !raw.toLowerCase().includes(query.toLowerCase())) return;
      count++;
      const details=document.createElement("details"); details.className="session"; details.id=`session-${n}`; details.open=Boolean(query);
      const summary=document.createElement("summary"); summary.textContent=`${s.timestamp} · 会话 ${n+1}`;
      const pre=document.createElement("pre"); pre.className="prose"; highlight(pre,raw,query);
      details.append(summary,pre); $("history-sessions").append(details);
    });
    $("search-count").textContent=query?`匹配 ${count} / ${view.sessions.length} 个会话。显示匹配会话的完整上下文；清空搜索可查看全部。`:`共 ${count} 个完整历史会话，按时间排列。点击日期展开原文。`;
  }
  function show() {
    const item=items[current], a=answers[current];
    $("question-title").textContent=`第 ${current+1} / ${items.length} 题 · ${taskNames[item.task]}`;
    $("task-description").textContent="只依据本题材料评价两条回复的实际质量。";
    $("question-select").value=String(current);
    $("rubric-zh").textContent=rubrics[item.task];
    const rubric=sheet.instrument.task_rubrics[item.task];
    addList("rubric-en",rubric.judge);
    $("material-example").textContent="Material difference example: "+rubric.material_example;
    $("not-material-example").textContent="Not material by itself: "+rubric.not_material_example;
    $("evidence-en").textContent=rubric.evidence_instruction||"";
    $("dg-policy").hidden=item.task!=="DG";
    $("dg-policy").textContent="相关摘录不是完整历史；摘录中未出现，不等于事实为假。可查完整历史，区分用户陈述与支持者猜测，注意日期及当前状态。证据仍不足时可选无法可靠判断。";
    $("task-input").textContent=item.task_input;
    $("input-title").textContent=(item.task==="ESC" || item.task==="DG")?"当前可见对话":"本题问题";
    $("response-a").textContent=item.response_A; $("response-b").textContent=item.response_B;
    $("reference-panel").hidden=item.reference_material===null;
    $("history-panel").hidden=item.task!=="DG"; $("history-panel").open=false;
    $("history-search").value="";
    $("history-date").replaceChildren(new Option("按日期查阅",""));
    if (item.task==="DG") {
      const view=sheet.reference_catalog[item.reference_id];
      $("reference-title").textContent="相关历史摘录";
      $("reference-note").textContent="这部分便于定位话题；核验其他历史细节和状态变化时，请查下方完整历史。";
      $("reference-excerpt").textContent=view.excerpt;
      $("history-summary").textContent=`完整过去历史 · ${view.sessions.length} 个会话 · 可搜索`;
      view.sessions.forEach((s,n)=>$("history-date").append(new Option(`${s.timestamp} · 会话 ${n+1}`,String(n))));
    } else {
      $("reference-title").textContent=item.task==="QA"?"参考答案":"参考总结";
      $("reference-note").textContent="按本题 reference 判断；无法核实的额外历史细节不要仅因未被提及就断言为假。";
      $("reference-excerpt").textContent=item.reference_material||"";
    }
    showHistory();
    for (const radio of document.querySelectorAll('input[name="verdict"]')) radio.checked=radio.value===a.verdict;
    $("rationale").value=a.rationale||"";
    $("previous").disabled=$("previous-top").disabled=current===0;
    $("next").disabled=$("next-top").disabled=current===items.length-1;
    refreshProgress();
  }
  function navigate(n) {
    capture(); current=Math.max(0,Math.min(items.length-1,n)); show(); persist();
    $("question-title").focus({preventScroll:true}); $("question-title").scrollIntoView({block:"start"});
  }
  function download(complete) {
    capture();
    if (complete && !answers.every(isComplete)) { message("请为每题填写判定和非空理由。",true); return; }
    const output=clone(sheet);
    output.items.forEach((i,n)=>{i.verdict=answers[n].verdict;i.rationale=answers[n].rationale;});
    const url=URL.createObjectURL(new Blob([JSON.stringify(output,null,2)+"\n"],{type:"application/json;charset=utf-8"}));
    const a=document.createElement("a"); a.href=url; a.download=payload.filename_stem+(complete?"_rated":"_progress")+".json";
    document.body.append(a); a.click(); a.remove(); setTimeout(()=>URL.revokeObjectURL(url),1000);
    dirtySinceExport=false;
    message(complete?"已请求下载完整答卷，请确认文件已保存，再交回研究负责人。":"已请求下载进度文件，请确认文件已保存。下次可导入此文件恢复。");
  }
  // Reject duplicate keys before a conflicting answer can be silently overwritten.
  function parseUniqueJSON(text) {
    let p=0;
    const space=()=>{while(/[\t\n\r ]/.test(text[p]||"~"))p++;};
    function string() {
      const start=p++;
      while(p<text.length) { if(text[p]==="\\") {p+=2;continue;} if(text[p++]==='"') return JSON.parse(text.slice(start,p)); }
      throw Error("JSON 字符串未结束。");
    }
    function value() {
      space(); const c=text[p];
      if(c==='"') return string();
      if(c==="{") {
        p++;space(); const o=Object.create(null), seen=new Set(); if(text[p]==="}"){p++;return o;}
        while(p<text.length) {
          space();if(text[p]!=='"')throw Error("JSON 对象字段无效。");const k=string();
          if(seen.has(k))throw Error("JSON 含重复字段，请保留原始文件并联系研究负责人。");seen.add(k);
          space();if(text[p++]!==":")throw Error("JSON 缺少冒号。");o[k]=value();space();
          if(text[p]==="}"){p++;return o;}if(text[p++]!==",")throw Error("JSON 对象格式无效。");
        }
      } else if(c==="[") {
        p++;space();const a=[];if(text[p]==="]"){p++;return a;}
        while(p<text.length){a.push(value());space();if(text[p]==="]"){p++;return a;}if(text[p++]!==",")throw Error("JSON 数组格式无效。");}
      } else {
        const m=/^(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/.exec(text.slice(p));
        if(m){p+=m[0].length;return JSON.parse(m[0]);}
      }
      throw Error("JSON 格式无效。");
    }
    const result=value();space();if(p!==text.length)throw Error("JSON 含额外内容。");return result;
  }
  async function importFile(file) {
    if(!file)return;
    try {
      const imported=parseUniqueJSON(await file.text());
      if(stable(withoutRatings(imported))!==originalStructure)throw Error("文件与本人的 V2 题目不一致。只能导入同一评审、同一版本且未改动题目的答卷。");
      const candidate=validAnswers(imported.items);
      const hasCurrent=answers.some(a=>a.verdict!==null || a.rationale!==null);
      if(hasCurrent && stable(candidate)!==stable(answers) && !window.confirm("导入文件将替换当前浏览器中的填写进度。若尚未备份，请先取消并导出进度。确认导入？"))return;
      answers=candidate;
      current=Math.max(0,answers.findIndex(a=>!isComplete(a)));
      dirtySinceExport=false;show();persist();message("已恢复本人进度，题目与参考材料校验一致。");
    } catch(e) {message(`未导入：${e.message}`,true);}
    finally {$("import-file").value="";}
  }
  $("rater-label").textContent=sheet.rater_id==="RATER_A"?"评审 A 专用":"评审 B 专用";
  items.forEach((_,n)=>$("question-select").append(new Option(`第 ${n+1} 题`,String(n))));
  addList("english-common",sheet.instrument.common_instruction);
  try {
    const raw=localStorage.getItem(key);
    if(raw) {
      const saved=parseUniqueJSON(raw);
      if(saved.sheet_sha256!==payload.sheet_sha256)throw Error("本机记录版本不符。");
      answers=validAnswers(saved.answers); current=Number.isInteger(saved.current)?Math.max(0,Math.min(items.length-1,saved.current)):0;
      message("已恢复当前浏览器保存的本人进度。");
    }
  } catch(e) {message(`未自动恢复：${e.message} 可通过“恢复进度”导入备份文件。`,true);}
  for(const radio of document.querySelectorAll('input[name="verdict"]'))radio.addEventListener("change",capture);
  $("rationale").addEventListener("input",capture);
  $("previous").onclick=$("previous-top").onclick=()=>navigate(current-1);
  $("next").onclick=$("next-top").onclick=()=>navigate(current+1);
  $("question-select").onchange=e=>navigate(Number(e.target.value));
  $("history-search").oninput=e=>showHistory(e.target.value);
  $("history-clear").onclick=()=>{$("history-search").value="";$("history-date").value="";showHistory();};
  $("history-date").onchange=e=>{
    if(e.target.value==="")return;$("history-search").value="";showHistory();const el=$(`session-${e.target.value}`);
    if(el){el.open=true;el.scrollIntoView({block:"start"});}
  };
  $("export-progress").onclick=()=>download(false);$("export-complete").onclick=()=>download(true);
  $("import-button").onclick=()=>$("import-file").click();
  $("import-file").onchange=e=>importFile(e.target.files[0]);
  window.addEventListener("beforeunload",e=>{if(dirtySinceExport){e.preventDefault();e.returnValue="";}});
  show();persist();
})();
