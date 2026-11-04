"""Load and verify existing public-source catalogs/tokenizers, never weights."""
from dataclasses import replace
import json
from pathlib import Path

from .evidence import prefix_from_dict
from .resource_organization import OrganizationCatalog, OrganizedItem, OrganizedRenderer
from .schema import digest
from .supervised_learning import file_sha


def read(p): return json.loads(Path(p).read_text())


def load_materials(package, *, prefix_ids=None, tokenizer=None):
    for name,h in read(package/'PACKAGE_MANIFEST.json').items():
        if Path(name).is_absolute() or '..' in Path(name).parts or file_sha(package/name)!=h:
            raise ValueError('source package changed')
    sources=read(package/'INPUT_HASHES_PRIVATE.json')
    for name,h in sources.items():
        if file_sha(name)!=h: raise ValueError('source changed: '+name)
    c=read(package/'CONFIG.json')
    if tokenizer is None:
        from transformers import AutoTokenizer
        tokenizer=AutoTokenizer.from_pretrained(c['runtime']['model_dir'],local_files_only=True)
    from metacom_pm.paper1.llama_tokenizer import LLAMA_TOKENIZER_JSON_SHA256
    renderer=OrganizedRenderer(count_text=lambda s:len(tokenizer.encode(s,add_special_tokens=False,truncation=False)),
        count_chat=lambda ms:len(tokenizer.apply_chat_template(ms,tokenize=True,add_generation_prompt=True)),
        tokenizer_identity=digest(dict(tokenizer=LLAMA_TOKENIZER_JSON_SHA256,template=tokenizer.chat_template)),
        context_limit=c['runtime']['policy']['context_limit'])
    if renderer.identity!=c['renderer_identity']: raise ValueError('renderer identity changed')
    paths=[p for p in sources if p.endswith('/RS_LIBRARY_PRIVATE.json')]
    if len(paths)!=1: raise ValueError('one original RS library required')
    library=read(paths[0]);items={x['key']:OrganizedItem(**x) for x in library['items']}
    if digest([x.identity for x in items.values()])!=library['identity']: raise ValueError('RS library changed')
    selected=set(c['initial_prefixes']) if prefix_ids is None else set(prefix_ids)
    if not selected<=set(c['initial_prefixes']): raise ValueError('outside initial train source scope')
    catalogs={}
    for pid in sorted(selected):
        src=read(package/'sources_private'/(pid+'.json'));stored=read(src['stored_source_path'])
        if src['stored_source_path'] not in sources: raise ValueError('unbound catalog')
        metadata=stored['frozen_RS_metadata']
        local=[replace(v,original_rank=metadata[k][0],bge_similarity=metadata[k][1]) if k in metadata else v for k,v in items.items()]
        local += [OrganizedItem(**x) for x in stored['memory']]
        prefix=prefix_from_dict(src['prefix'])
        catalog=OrganizationCatalog(prefix,local,provenance_identity=stored['catalog_identity'])
        if prefix.identity!=pid or prefix.split!='train' or catalog.identity!=src['catalog_identity']:
            raise ValueError('catalog lineage changed')
        catalogs[pid]=catalog
    return c,catalogs,renderer
