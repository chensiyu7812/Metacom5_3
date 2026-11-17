"""Run the committed B v2 input builder with A's RS catalog (CPU tokenizer only).

The B checkout is read-only and must be clean. Only its needs subpackage is
used; source registry, bank, frozen C0 and the catalog come from this A tree.
This is a cross-line input compatibility check, not a model/writer execution.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def main():
    ap=argparse.ArgumentParser(__doc__)
    ap.add_argument('--a-root',type=Path,default=Path(__file__).resolve().parents[3])
    ap.add_argument('--b-root',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();a=args.a_root.resolve();b=args.b_root.resolve()
    b_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=b,text=True).strip()
    assert b_sha=='d06715bf6893710c8b21f2c91c7cac42c0111e85'
    assert not subprocess.check_output(['git','status','--porcelain'],cwd=b,text=True).strip()
    sys.path.insert(0,str(a/'project/src'))
    import metacom_pm.rl1v3.needs as needs
    needs.__path__[:]=[str(b/'project/src/metacom_pm/rl1v3/needs')]
    from metacom_pm.rl1v3.needs import protocol_v2 as W
    from metacom_pm.rl1v3.needs.sources import a1_context
    from metacom_pm.rl1v3.bank.v0_port import load_bank
    from metacom_pm.rl1v3.bank.rs_v0_catalog import load as load_catalog
    from metacom_pm.rl1v3.retrieve.native_tokens import NativeTokenizer
    from metacom_pm.rl1v3.io import file_sha256,write_json_once,write_jsonl_once,object_sha256
    bank,_=load_bank(a)
    catalog_path=a/'project/outputs/pm_rl1/v3/A1b_crossline_20261118/RS_V0_STRATEGY_CATALOG.json'
    catalog=load_catalog(catalog_path,root=a,bank=bank)
    tok=NativeTokenizer('/opt/tokkio-data0/tokkio_models/paper1_judges/qwen35_9b',a/'project/outputs/pm_rl1/v3/A1_reuse/ASSET_REUSE_MANIFEST.json')
    def count(messages):
        return len(tok.tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,enable_thinking=False))
    coverage=a/'project/outputs/pm_rl1/v3/B1/coverage_sample_v1.jsonl'
    rows=[json.loads(x) for x in coverage.read_text().splitlines()];results=[]
    for row in rows:
        ctx=a1_context(bank.registry,row)
        kw=dict(registry=bank.registry,count_prompt=count,native_context_tokens=tok.native_context_tokens,
                operational_max_input_tokens=32768,tokenizer_identity=tok.identity)
        pack=W.build_pack(ctx,catalog,**kw)
        assert pack['status']=='ready'
        assert W.build_pack(ctx,None,**kw)['status']=='blocked_catalog'
        msgs=W.render_messages(pack)
        assert 'NOT validated or professional methods' in msgs[0]['content']
        data=json.loads(msgs[1]['content'].split('\n',1)[1])
        assert len(data['METHOD_LABELS'])==7
        assert all(label['definition']=='unknown' for label in data['METHOD_LABELS'])
        results.append(dict(prefix_id=ctx.prefix.prefix_id,pack_sha256=pack['pack_sha256'],status=pack['status'],
                            input_tokens=pack['input_tokens'],catalog_tokens=pack['catalog_tokens'],
                            source_version=pack['source_version'],catalog_id=catalog.catalog_id,
                            messages_sha256=object_sha256(msgs),uses=row['uses']))
    assert len(results)==24
    write_jsonl_once(args.out/'B1_V2_CATALOG_INPUTS.jsonl',results)
    modules=[]
    for name,module in list(sys.modules.items()):
        filename=getattr(module,'__file__',None)
        if not filename:continue
        path=Path(filename).resolve()
        if not path.is_file() or not path.is_relative_to(b/'project/src'):continue
        blob=subprocess.check_output(['git','show',b_sha+':'+str(path.relative_to(b))],cwd=b)
        import hashlib
        assert hashlib.sha256(blob).hexdigest()==file_sha256(path)
        modules.append(dict(module=name,path=str(path.relative_to(b)),sha256=file_sha256(path)))
    write_json_once(args.out/'B1_V2_CATALOG_PREFLIGHT.json',dict(a_code_sha=subprocess.check_output(
        ['git','rev-parse','HEAD'],cwd=a,text=True).strip(),b_code_sha=b_sha,b_modules=modules,
        script_sha256=file_sha256(Path(__file__)),catalog_id=catalog.catalog_id,catalog_file_sha256=file_sha256(catalog_path),
        coverage_sha256=file_sha256(coverage),prefixes=len(results),ready=24,tokenizer=tok.identity,
        tokenizer_files=tok.file_hashes,input_tokens_min=min(r['input_tokens'] for r in results),
        input_tokens_max=max(r['input_tokens'] for r in results),truncated=False,
        writer_calls=0,gpu_used=False,weights_loaded=False,paid_calls=0))


if __name__=='__main__':main()
