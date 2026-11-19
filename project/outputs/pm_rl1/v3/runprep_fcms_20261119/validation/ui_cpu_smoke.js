// Node DOM harness: interaction/serialization checks, not browser visual acceptance.
const fs=require("fs"),vm=require("vm"),assert=require("assert");
const page=fs.readFileSync(process.argv[2],"utf8");
const elements={},downloads=[],blobs=[];
class E {
 constructor(tag){this.tag=tag;this.value="";this.textContent="";this.children=[];this.checked=false;}
 append(...xs){this.children.push(...xs);if(this.tag==="select"&&!this.value&&xs[0])this.value=xs[0].value;}
 replaceChildren(){this.children=[];this.value="";}
 click(){downloads.push(this);}
}
for(const m of page.matchAll(/<(\w+)[^>]*\bid="([^"]+)"/g))elements[m[2]]=new E(m[1]);
const context={
 document:{getElementById:id=>elements[id],createElement:t=>new E(t)},
 TextDecoder,Uint8Array,atob,Date,Error,JSON,String,Number,
 Blob:class {constructor(parts){this.parts=parts;blobs.push(this);}},
 URL:{createObjectURL:()=> "blob:fixture",revokeObjectURL:()=>{}},setTimeout:()=>{},
};
vm.runInNewContext(page.match(/<script>([\s\S]*?)<\/script>/)[1],context);
assert.equal(elements.prefix.children.length,8);
assert(elements.current.textContent.length>0);
assert(elements.history.children.length>0);
elements.selector.value="CPU_FIXTURE_NOT_HUMAN";
elements.need.value="fixture";elements.rationale.value="fixture";
elements.decision.value="none_suitable";elements.decision.onchange();
elements.download.onclick();assert.equal(downloads.length,0);
elements.blind.checked=true;elements.download.onclick();
assert.equal(downloads.length,1);
const draft=JSON.parse(blobs[0].parts[0]);
assert.equal(draft.selected_record_id,null);assert.equal(draft.decision,"none_suitable");
assert.equal(draft.outcomes_not_seen,true);assert.equal(draft.prefix_id.length,64);
elements.prefix.value="1";elements.prefix.onchange();
assert.equal(elements.need.value,"");assert.equal(elements.blind.checked,false);
assert(!page.includes(".innerHTML"));assert(page.includes("connect-src 'none'"));
console.log(JSON.stringify({status:"PASS",prefixes:8,mechanism:"Node DOM harness",
 downloads_are_test_fixtures:true,real_human_receipts:0,model_calls:0,browser_visual_review:"not performed"}));
