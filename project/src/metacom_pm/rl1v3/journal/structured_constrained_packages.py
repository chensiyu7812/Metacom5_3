"""Prepare two immutable, independently unapproved 18-call diagnostic packages."""
import json,shutil,sys
from pathlib import Path
from ..io import file_sha256,object_sha256,write_json_once,write_jsonl_once
from . import structured_constrained_run as R
from .structured_constrained import PROTOCOL,SCHEMA

def prepare(original,repo,out):
    original,repo,out=map(Path,(original,repo,out));out.mkdir(parents=True,exist_ok=False)
    executor=out/'executor';shutil.copytree(original/'executor',executor,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    names=['project/src/metacom_pm/rl1v3/journal/'+n for n in (
        'structured_constrained.py','structured_constrained_run.py','structured_constrained_worker.py')]
    names.append('project/scripts/rl1v3/journal_structured_constrained.py')
    for name in names:shutil.copy2(repo/name,executor/name)
    import xgrammar
    import importlib.metadata
    src=Path(xgrammar.__file__).parent;vendor=executor/'vendor_constrained'
    vendor.mkdir();shutil.copytree(src,vendor/'xgrammar',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    dist=importlib.metadata.distribution('xgrammar')
    for p in src.parent.glob('xgrammar-*.dist-info'):shutil.copytree(p,vendor/p.name)
    vendor_hashes={str(p.relative_to(vendor)):file_sha256(p) for p in vendor.rglob('*') if p.is_file()}
    runtime_files={}
    for name,module in list(sys.modules.items()):
        if name.split('.')[0] in ('numpy','pydantic','pydantic_core','typing_extensions','packaging'):
            path=getattr(module,'__file__',None)
            if path and Path(path).is_file():runtime_files[path]=file_sha256(path)
    constraint=dict(protocol=PROTOCOL,schema=SCHEMA,xgrammar_version=dist.version,
        full_vocabulary_size=262144,stop_token_ids=[1,106,50],format_only=True,
        semantic_enums=False,task_specific_schema=False,posthoc_repair=False,
        input_unchanged=True,original_decode_parameters_unchanged=True,
        limitations=['schema compiler uses property order; values remain arbitrary strings',
          'max_new_tokens can terminate before grammar completion; no forced close or retry',
          'CPU tests do not establish GPU execution or factual correctness'])
    constraint_path=out/'CONSTRAINT_CONSTRAINED.json';write_json_once(constraint_path,constraint)
    catalog=[]
    for n in (1,2):
        op=original/f'batch-{n:02d}/PLAN.json';old,rows,_=R.S.check(op)
        batch=out/f'batch-{n:02d}';batch.mkdir();cs=object_sha256(constraint)
        newrows=[dict(r,original_request_id=r['request_id'],constraint_sha256=cs,
            request_id=R.constrained_request_id(r,cs)) for r in rows]
        requests=batch/'REQUESTS_CONSTRAINED.private.jsonl';write_jsonl_once(requests,newrows)
        plan=dict(old,protocol=R.RUN_PROTOCOL,job_kind=R.JOB_KIND,executor_root=str(executor),
            original_plan_path=str(op),original_plan_sha256=object_sha256(old),
            constraint_path=str(constraint_path),constraint_sha256=cs,vendor_path=str(vendor),
            vendor_files_sha256=vendor_hashes,constraint_runtime_files_sha256=runtime_files,
            requests_path=str(requests),requests_sha256=file_sha256(requests),
            ordered_request_ids=[r['request_id'] for r in newrows],
            executor_files_sha256=dict(old['executor_files_sha256'],**{name:file_sha256(executor/name) for name in names}),
            files_sha256=dict(old['files_sha256'],**{str(op):file_sha256(op),str(constraint_path):file_sha256(constraint_path),str(requests):file_sha256(requests)}))
        target=batch/'PLAN_CONSTRAINED.json';write_json_once(target,plan);R.check(target)
        write_json_once(batch/'APPROVAL_CONSTRAINED_TEMPLATE.json',dict(protocol=R.RUN_PROTOCOL,job_kind=R.JOB_KIND,
            authorized=False,plan_sha256=object_sha256(plan),max_calls=18,max_model_loads=1,researcher='',decision_evidence=''))
        catalog.append(dict(batch=n,plan_path=str(target),plan_sha256=object_sha256(plan),
            plan_file_sha256=file_sha256(target),logical=18,physical=18,input_tokens=sum(r['input_tokens'] for r in newrows),authorized=False))
    result=dict(protocol='structured36-constrained-catalog-v1',calls=36,authorized=False,
        constraint_sha256=object_sha256(constraint),batches=catalog,model_loads_requested=2,gpu_calls_executed=0)
    write_json_once(out/'CATALOG_CONSTRAINED.json',result);return result
