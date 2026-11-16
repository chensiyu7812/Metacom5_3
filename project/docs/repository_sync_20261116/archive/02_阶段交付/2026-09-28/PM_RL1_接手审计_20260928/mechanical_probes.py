"""Bounded offline reproductions using temporary ledgers, never the live ledger."""
import ast
import json
import sys
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path('/home/tokkio/Metacom5_3').resolve()
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'project/src'))
from metacom_pm.paper1.api_budget import CumulativePaper1ApiBudgetLedger
from metacom_pm.paper1.core.treatment import parse_resource_blocks

results = {}
with TemporaryDirectory() as directory:
    p=Path(directory)/'parallel.jsonl'
    a=CumulativePaper1ApiBudgetLedger(p,opening_cost_usd=Decimal('0'))
    b=CumulativePaper1ApiBudgetLedger(p,opening_cost_usd=Decimal('0'))
    for index,ledger in enumerate([a,b]):
        ledger.reserve(reservation_id=str(index),logical_call_id=str(index),call_hash=str(index),
            stage='offline_probe',provider='NO_PROVIDER_CALLED',model='none',maximum_cost_usd=Decimal('30'),call_class='PRIMARY')
    events=[json.loads(x) for x in p.read_text().splitlines()]
    results['independent_instances_without_external_transaction']={
        'both_30_usd_reservations_accepted':len(events)==2,
        'total_reserved':str(sum(Decimal(e['maximum_cost_usd']) for e in events)),
        'meaning':'The ledger class alone is not a shared atomic gateway. This does not demonstrate a historical overrun.'}
    path=ROOT/'project/scripts/paper1/83_submit_official_static_scoring_batch.py'
    tree=ast.parse(path.read_text())
    expression=next(kw.value for node in ast.walk(tree) if isinstance(node,ast.Call)
        and isinstance(node.func,ast.Attribute) and node.func.attr=='settle'
        for kw in node.keywords if kw.arg=='actual_cost_usd')
    observed=Decimal('.12');reserved=Decimal('.10')
    argument=eval(compile(ast.Expression(expression),str(path),'eval'),{'__builtins__':{},'min':min},
        {'actual':observed,'worst_case':reserved})
    ledger=CumulativePaper1ApiBudgetLedger(Path(directory)/'batch.jsonl',opening_cost_usd=Decimal('0'))
    reservation=ledger.reserve(reservation_id='batch',logical_call_id='batch',call_hash='batch',stage='offline_probe',
        provider='NO_PROVIDER_CALLED',model='none',maximum_cost_usd=reserved,call_class='PRIMARY')
    ledger.settle(reservation,actual_cost_usd=argument,outcome='SUCCEEDED',allow_overrun=observed>reserved)
    results['batch_overrun_settlement']={'source_expression':ast.unparse(expression),'line':expression.lineno,
        'hypothetical_actual_usd':str(observed),'ledger_recorded_usd':str(ledger.accounted_cost_usd),
        'meaning':'Batch path clips actual before settlement, unlike the repaired synchronous path; no live Batch was run.'}
malformed='<PAPER1_RESOURCE>\nnot-json\nprobe content\n</PAPER1_RESOURCE>'
results['malformed_resource_block']={'delimiter_present':True,'parsed_blocks':len(parse_resource_blocks(malformed)),
    'meaning':'Parser silently skips this block. RL1 must reject damaged/extra delimiters at the envelope boundary.'}
(OUT/'mechanical_probe_results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(results,ensure_ascii=False,indent=2))
