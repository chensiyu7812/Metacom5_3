"""Join measured reads with quarantined source-section metadata; no rereads/models."""
import argparse,json
from collections import Counter
from pathlib import Path
from metacom_pm.rl1v3.io import file_sha256,write_json_once


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[3])
    p.add_argument('--measured',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    original=a.measured/'ASSET_CONVERSION_SCORECARD.json';score=json.loads(original.read_text())
    audit=json.loads((a.root/'project/outputs/pm_rl1/v3/A1_reuse/ASSET_REUSE_MANIFEST.json').read_text())
    ledger=a.root/'project/outputs/pm_rl1/v3/A1_reuse/ASSET_ITEMS.jsonl'
    if file_sha256(ledger)!=audit['item_ledger']['sha256']:raise ValueError('fixed asset ledger changed')
    excluded=[]
    for line in ledger.read_text().splitlines():
        row=json.loads(line)
        if not row['asset_kind'].startswith('EvoEmo_'):continue
        if row['classification']!='quarantine':raise ValueError('privileged section is not quarantined')
        score['assets'][row['asset_kind']]=dict(existing=row['count'],count_unit=row['count_unit'],
            source_verified=0,mapped_into_bank=0,successfully_read=0,status='quarantine',reason=row['reason'])
        excluded.append(dict(kind=row['asset_kind'],count=row['count'],count_unit=row['count_unit'],reason=row['reason']))
    score['source_sections_excluded_from_runtime']=excluded
    score['measured_scorecard_sha256']=file_sha256(original)
    score['asset_ledger_sha256']=file_sha256(ledger)
    score['definitions']={
        'source_verified':'Exact memory spans / RAW turns / legacy-normalized strategy response binding. Not semantic truth.',
        'lineage_verified':'Treatment parent source/family mapping only; atomic method text is not semantically verified.',
        'mapped_into_bank':'Old asset has explicit mapping to one or more real records; many-to-one RS mappings are not independent records.',
        'successfully_read':'At least one mapped record actually delivered in the complete 4119-prefix CPU run; not recall relevance or support quality.',
        'unavailable':'For read attempts: no legal candidate. For bank records: never eligible under this fixed B0 prefix census, not globally unusable.'}
    score['total_read_attempts']=sum(v['attempts'] for v in score['read_metrics'].values())
    score['total_read_successes']=sum(v['success'] for v in score['read_metrics'].values())
    score['get_success_rate']=score['total_read_successes']/score['total_read_attempts']
    score['records_never_eligible_in_fixed_B0']=sum(score['heads'].values())-sum(v['distinct_eligible_records'] for v in score['read_metrics'].values())
    score['migration_status_counts_distinct_ledger_rows']=dict(Counter(json.loads(l)['status'] for l in (a.measured/'bank/migration.jsonl').read_text().splitlines()))
    write_json_once(a.out,score)
if __name__=='__main__':main()
