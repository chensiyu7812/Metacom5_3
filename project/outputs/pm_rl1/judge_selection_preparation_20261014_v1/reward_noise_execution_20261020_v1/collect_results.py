"""Read only completed records; write a new derived snapshot, never original scores."""
from pathlib import Path
import sys,json,csv,io,time,hashlib
sys.path.insert(0,str(Path(__file__).resolve().parent))
import noise as n
from noise import s,p
import analysis as a
from adapters import final_content
from deepseek_access import cost_from_usage

def collect():
    protocol,items=n.load();proposal=s.read(n.PROPOSAL/'proposal.json')
    starts,results=p.replay(n.ROOT,protocol)
    stats=a.calculate(proposal,protocol,results)
    summary=n.summarize(protocol,n.ROOT,n.historical_count())
    records=[];parts=[];usage_estimates=[]
    for slot in protocol['schedule']:
        sid=slot['slot_id'];row=results.get(sid);ev=row['evaluation'] if row else {}
        rawpath=n.ROOT/(sid+'.response.json')
        raw=s.read(rawpath) if row and rawpath.exists() else None
        final=None;finish=None
        if raw:
            final,finish=final_content(raw)
            usage_estimates.append(cost_from_usage(raw))
        rec=dict(**slot,started=sid in starts,result_received=row is not None,
            request_identity=starts[sid]['request_identity'] if sid in starts else None,
            technical_valid=row['technical_valid'] if row else None,model_unknown=ev.get('model_unknown'),
            q=ev.get('q'),m=ev.get('m'),U=ev.get('U'),full_final=final,finish=finish,
            final_sha256=hashlib.sha256(final.encode()).hexdigest() if final is not None else None,
            parsed=ev.get('value'),mechanical_failure=ev.get('error') or ev.get('measurement',{}).get('measurement_status') if row and not row['technical_valid'] else None,
            elapsed_seconds=row['elapsed_seconds'] if row else None,usage=row.get('usage') if row else None,
            financial=row['financial'] if row else None,fingerprint=row.get('fingerprint') if row else None,
            reviewer_disputes='pending_separate_source_audit',human_reference='pending',reward_eligible=False,
            paths={k:str(n.ROOT/(sid+'.'+k)) for k in ('request.json','started.json','response.json','result.json') if (n.ROOT/(sid+'.'+k)).exists()})
        records.append(rec)
        if final is not None:
            parts.append(f"## {slot['position']:02d} / round {slot['draw']} / {slot['endpoint']}\n\nrequest_id: {rec['request_identity']}\n\nq={rec['q']}, m={rec['m']}, U={rec['U']}; technical={rec['technical_valid']}; model_unknown={rec['model_unknown']}\n\n```json\n{final}\n```\n")
    usage_known=[x for x in usage_estimates if x.get('usage_price_estimate_usd') is not None]
    from decimal import Decimal
    summary['usage_price_estimate_usd']=str(sum((Decimal(x['usage_price_estimate_usd']) for x in usage_known),Decimal(0)))
    summary['usage_estimate_requests']=len(usage_known);summary['invoice_confirmed']=False
    summary['reasoning_tokens_subset']=sum((r['usage'].get('completion_tokens_details') or {}).get('reasoning_tokens',0) for r in results.values() if r.get('usage'))
    times=[r['started_unix'] for r in starts.values()]
    ends=[starts[k]['started_unix']+r['elapsed_seconds'] for k,r in results.items()]
    summary['scoring_window_seconds']=(max(ends)-min(times)) if ends and times else None
    return records,stats,summary,'\n'.join(parts)

if __name__=='__main__':
    out=n.HERE/('derived_'+str(time.time_ns()));out.mkdir(mode=0o700)
    records,stats,summary,finals=collect()
    for name,data in [('per_request_results.json',records),('statistics.json',stats),('summary.json',summary)]:s.save(out/name,data)
    (out/'ALL_COMPLETE_FINALS.md').write_text('# Complete final channel only; not independent human ratings\n\n'+finals)
    table=io.StringIO();fields=['position','draw','block','endpoint','started','technical_valid','model_unknown','q','m','U','elapsed_seconds']
    writer=csv.DictWriter(table,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(records);(out/'SLOTS_48.csv').write_text(table.getvalue())
    print(s.canonical(dict(snapshot=str(out),started=summary['started'],technical_complete=summary['technical_complete'],stats=stats['summary'],accounted=summary['accounted_usd'])))
