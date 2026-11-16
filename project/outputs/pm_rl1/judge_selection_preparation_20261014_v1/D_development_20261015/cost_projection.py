"""Descriptive usage projection, not execution or 128/384 selection."""
import json,statistics
from decimal import Decimal as D
from pathlib import Path
out=Path(__file__).resolve().parent;data=json.loads((out/'results_private.json').read_text());rows=[r for r in data['rows'] if r['started'] and r.get('usage')]
mean=lambda xs:sum(xs,D(0))/D(len(xs))
observed=mean([D(r['usage_price_estimate_usd']) for r in rows]);peak=mean([D(r['accounted_upper_usd']) for r in rows]);off_uncached=peak/2
low=min(D(r['usage_price_estimate_usd']) for r in rows);high=max(D(r['accounted_upper_usd']) for r in rows)
latency=statistics.mean(r['elapsed_seconds'] for r in rows)
scenarios=[]
for name,n in [('conditional_remaining_D',40-len(rows)),('conditional_unique_winner_acceptance',59),('core_128_not_selected',2817),('core_384_not_selected',4353),('optional_RQX_semantic_recovery',576),('core128_plus_acceptance_plus_optional',2817+59+576),('core384_plus_acceptance_plus_optional',4353+59+576)]:
 scenarios.append(dict(name=name,judge_slots=n,empirical_mean_cost_range_usd=[str(observed*n),str(peak*n)],offpeak_uncached_mean_usd=str(off_uncached*n),observed_per_call_extreme_envelope_usd=[str(low*n),str(high*n)],serial_response_hours=latency*n/3600,native_maximum_reservation_usd=str(D('.786432')*n)))
value=dict(measured_D_attempts=len(rows),unit_observed_cache_time_mean_usd=str(observed),unit_peak_uncached_mean_usd=str(peak),unit_observed_min_to_peak_uncached_max_usd=[str(low),str(high)],input_tokens_mean=statistics.mean(r['usage']['prompt_tokens'] for r in rows),output_tokens_min_mean_max=[min(r['usage']['completion_tokens'] for r in rows),statistics.mean(r['usage']['completion_tokens'] for r in rows),max(r['usage']['completion_tokens'] for r in rows)],scenarios=scenarios,caveats=['Observed development sample is clustered, selected by stop and small; no confidence interval or full-run guarantee','Provider prices, cache reuse, time of day, source length and reasoning tails can change cost','Core slot counts from existing budget; no scenario selected or authorized','Judge response wall only; excludes generation/local GPU/training/human review; no claim of total96h feasibility','Observed usage-pricing is not invoice reconciliation; shared ledger retains conservative peak/no-cache accounting'])
(out/'cost_projection.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');print(json.dumps(value,ensure_ascii=False,indent=2))
