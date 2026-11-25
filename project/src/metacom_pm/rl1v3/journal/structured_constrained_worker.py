"""Internal HF subprocess. Refuses standalone startup; no imports of torch at import time."""
from __future__ import annotations
import contextlib
import importlib.metadata
import json
import os
import platform
import sys
import time
from ..generator.runprep_checkpoint import check_loaded_model, read_header
from ..generator.limited_run import require

from .structured_constrained import compile_grammar, StructuredConstrainedProcessor

def main():
    parent=os.environ.get("PMRL1_LIMITED_SUPERVISOR_PID")
    require(parent and int(parent)==os.getppid(),"internal worker requires admitted supervisor")
    wire=sys.stdout
    model=tok=torch=gc_class=None;spec=None;loaded=False
    for line in sys.stdin:
        try:
            command=json.loads(line)
            with contextlib.redirect_stdout(sys.stderr):
                if command["operation"]=="load":
                    require(not loaded,"one model load only");loaded=True
                    spec=command["spec"];path=command["model_path"];report=command["checkpoint"]
                    require(report["structural_match"] and report["architecture"]==spec["model"]["architecture"],"checkpoint structure")
                    require(platform.python_version()==spec["runtime"]["python"],"Python version")
                    for name,version in spec["runtime"]["packages"].items():
                        if name!="vllm":require(importlib.metadata.version(name)==version,"package "+name)
                    for h in report["headers"]:
                        require(read_header(os.path.join(path,h["file"]))[1]==h,"checkpoint header")
                    import torch
                    from transformers import AutoTokenizer, AutoModelForMultimodalLM, GenerationConfig
                    gc_class=GenerationConfig
                    torch.set_num_threads(1);torch.manual_seed(0);torch.use_deterministic_algorithms(True)
                    torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
                    t=time.monotonic()
                    tok=AutoTokenizer.from_pretrained(path,local_files_only=True,trust_remote_code=False)
                    from pathlib import Path
                    import xgrammar
                    require(Path(xgrammar.__file__).resolve().is_relative_to(Path(os.environ['PMRL1_CONSTRAINED_VENDOR']).resolve()),'isolated grammar dependency required')
                    require(importlib.metadata.version('xgrammar')=='0.1.21','frozen grammar package')
                    from transformers import AutoConfig
                    config=AutoConfig.from_pretrained(path,local_files_only=True,trust_remote_code=False)
                    grammar_started=time.monotonic()
                    grammar=compile_grammar(tok,vocab_size=config.text_config.vocab_size,eos_token_ids=spec['decode']['eos_token_id'])
                    grammar_compile_seconds=time.monotonic()-grammar_started
                    model,info=AutoModelForMultimodalLM.from_pretrained(path,local_files_only=True,
                        trust_remote_code=False,ignore_mismatched_sizes=False,output_loading_info=True,
                        dtype=torch.bfloat16,attn_implementation="sdpa")
                    diagnostic=check_loaded_model(model,info,report)
                    model=model.to("cuda:0").eval();torch.cuda.synchronize()
                    result={"seconds":time.monotonic()-t,"loading":diagnostic,"architecture":type(model).__name__,
                            "grammar_compile_cpu_seconds":grammar_compile_seconds,
                            "peak_allocated_bytes":torch.cuda.max_memory_allocated(),"peak_reserved_bytes":torch.cuda.max_memory_reserved()}
                elif command["operation"]=="generate":
                    require(model is not None,"load required");p=command["payload"]
                    require(set(p)=={"messages","input_ids","decode"} and p["decode"]==spec["decode"],"payload whitelist/decode")
                    ids=tok.apply_chat_template(p["messages"],tokenize=True,add_generation_prompt=True,enable_thinking=False,return_dict=False)
                    require(list(ids)==p["input_ids"],"native tokenizer differs")
                    require(len(ids)+320<=16384,"capacity")
                    inp=torch.tensor([ids],device="cuda:0");mask=torch.ones_like(inp)
                    gc=gc_class.from_pretrained(path,local_files_only=True)
                    for k,v in p["decode"].items():
                        if k not in {"seed","enable_thinking"}:setattr(gc,k,v)
                    torch.manual_seed(0);torch.cuda.reset_peak_memory_stats()
                    processor=StructuredConstrainedProcessor(grammar)
                    t=time.monotonic()
                    with torch.inference_mode():generated=model.generate(inp,attention_mask=mask,generation_config=gc,logits_processor=[processor])
                    torch.cuda.synchronize();seconds=time.monotonic()-t
                    ids_out=generated[0,len(ids):].tolist();eos=p["decode"]["eos_token_id"]
                    stop=next((i+1 for i,x in enumerate(ids_out) if x in eos),len(ids_out));ids_out=ids_out[:stop]
                    result={"token_ids":ids_out,"text":tok.decode(ids_out,skip_special_tokens=True),
                            "finish_reason":"eos" if ids_out and ids_out[-1] in eos else "length",
                            "seconds":seconds,"input_tokens":len(ids),
                            "output_tokens_per_second":len(ids_out)/seconds if seconds else None,
                            "peak_allocated_bytes":torch.cuda.max_memory_allocated(),"peak_reserved_bytes":torch.cuda.max_memory_reserved(),
                            "timing_scope":"synchronized local single HF call; not user-visible end-to-end latency"}
                    result['constraint_measurement']=processor.measurement()
                    del inp,mask,generated
                else:raise ValueError("unknown worker operation")
            wire.write(json.dumps({"ok":True,"result":result})+"\n");wire.flush()
        except BaseException as exc:
            wire.write(json.dumps({"ok":False,"error":type(exc).__name__+": "+str(exc)})+"\n");wire.flush()
            return 1
    return 0
if __name__=="__main__":raise SystemExit(main())

