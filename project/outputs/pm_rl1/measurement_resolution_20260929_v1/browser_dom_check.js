const fs=require('fs'),vm=require('vm'),assert=require('assert');
const data=fs.readFileSync('/tmp/pm_rl1_browser_data.json','utf8'),registry=new Map();
class Element {
 constructor(tag){this.tag=tag;this.children=[];this.selectedIndex=0;this.checked=false;this._value='';this.textContent='';}
 append(...items){this.children.push(...items)}
 replaceChildren(...items){this.children=[...items];this.selectedIndex=0}
 set id(value){this._id=value;registry.set(value,this)}
 get id(){return this._id}
 set value(value){if(this.tag==='select'){this.selectedIndex=this.children.findIndex(x=>x.value===value)}else this._value=value;}
 get value(){return this.tag==='select'?(this.children[this.selectedIndex]?.value??''):this._value}
 scrollIntoView(){}
}
for(const id of ['data','filter','case','prev','next','all','overview','sources','sourcecount','title','state','need','reply','audit','quality','qrefs','assessments','coverage','raw']){const e=new Element(['case','filter'].includes(id)?'select':'div');e.id=id;}
registry.get('data').textContent=data;
const document={getElementById:id=>registry.get(id),createElement:tag=>new Element(tag)};
vm.runInNewContext(fs.readFileSync('/tmp/pm_rl1_evidence_browser_check.js','utf8'),{document,JSON,Set,Number});
const filter=registry.get('filter'),cases=registry.get('case');let checks=0;
for(let f=0;f<filter.children.length;f++){
 filter.selectedIndex=f;filter.onchange();
 for(let i=0;i<cases.children.length;i++){
  cases.selectedIndex=i;cases.onchange();assert(registry.get('title').textContent);assert(registry.get('reply').textContent);
  registry.get('all').checked=true;registry.get('all').onchange();assert(registry.get('sources').children.length>0);
  registry.get('all').checked=false;registry.get('all').onchange();
  const refs=registry.get('qrefs').children;if(refs.length)refs[0].onclick();checks++;
 }
 registry.get('prev').onclick();registry.get('next').onclick();
}
console.log(JSON.stringify({status:'DOM_EVENT_SMOKE_PASSED',rows:JSON.parse(data).rows.length,filtered_record_checks:checks,visual_browser_test:false}));
