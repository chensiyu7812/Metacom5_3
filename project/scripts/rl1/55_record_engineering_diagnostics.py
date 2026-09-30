#!/usr/bin/env python3
"""Evidence-bound read-through observations, not a calibrated quality score."""
from collections import Counter
import json
from pathlib import Path
import statistics
import sys
PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1.schema import digest
from metacom_pm.io import sha256_file
OUT=PROJECT/'outputs/pm_rl1/source_repair_20260929_v2'
ENG=PROJECT/'outputs/pm_rl1/executor_engineering_20260929_v1'
NOTES={
(13,'OFF'):('Both reflect current work/anxiety and offer further discussion. LoRA is shorter; no efficacy inference.',[]),
(13,'R'):('Both ask about therapist using source-visible therapy history. No new improvement in history utilization established.',['historical_uptake_both']),
(13,'L'):('Both focus on current work/anxiety without inventing outcomes from the generic support-seeking ME.',[]),
(14,'OFF'):('Base invites further discussion; LoRA only validates vulnerability. Shorter is not automatically worse, but adequacy needs independent assessment.',['lora_brief_generic']),
(14,'R'):('LoRA restates vulnerability/helping tension without specific supplied coping history. Base also does not explicitly use historical details.',['lora_brief_generic']),
(14,'L'):('Neither repeats the author teacher error that swapped friend and user struggles. LoRA remains a short reflection.',[]),
(15,'OFF'):('Base invites discussion of proposed contribution; LoRA ends after acknowledging discouragement. No factual contradiction identified.',['lora_brief_generic']),
(15,'R'):('Base reasks details already stated; LoRA repeats discouragement without advancing the current issue. Neither provides clear historical benefit.',['lora_brief_generic']),
(15,'L'):('BOTH invent assistant personal experience: I have been in similar situations. RS is an optional archived move, not proof the assistant lived it.',['invented_assistant_experience_both']),
(16,'OFF'):('Both engage with thesis perspective; LoRA asks for the changed perspective rather than assuming progress.',[]),
(16,'R'):('Both ask what changes for thesis work. No strong additional historical uptake beyond current input.',[]),
(16,'L'):('Base reassures and offers support; LoRA asks about the new perspective. Both ignore unsupported assistant self-experience.',[]),
(17,'OFF'):('Base suggests discussing feelings with mother; burden implications deserve care. LoRA gives only a generic one-sentence acknowledgment.',['lora_brief_generic']),
(17,'R'):('Base grounds reassurance in current caregiving. LoRA only says it is tough to feel not doing enough; no specific history or next conversational move.',['lora_brief_generic']),
(17,'L'):('Base asks about doctors or concrete desired help. LoRA gives a generic one-sentence acknowledgment. All end in native EOT, not a token cap.',['lora_brief_generic']),
(18,'OFF'):('LoRA becomes much longer and gives workplace options; base asks for impact. Length increase is not a demonstrated quality gain.',['lora_longer_advice']),
(18,'R'):('Both ask about available support. LoRA introduces HR as an optional contact, not a claim that the user already contacted HR.',[]),
(18,'L'):('Base does not use Annie. LoRA correctly mentions source-supported sister Annie and possible listening/advice. This shows uptake, not proven benefit for the work problem.',['historical_uptake_lora_only'])}

def main():
    run=Path(json.loads((ENG/'diagnostic_pointer.json').read_text())['run_dir'])
    summary=json.loads((run/'summary.json').read_text());pairs={}
    for row in summary['rows']:pairs.setdefault((row['index'],row['condition']),{})[row['arm']]=row
    assert set(pairs)==set(NOTES)
    output=[]
    for key in sorted(pairs):
        pair=pairs[key];assert set(pair)=={'base','lora'}
        raw={arm:json.loads((run/(row['request_id']+'.raw.json')).read_text()) for arm,row in pair.items()}
        req={arm:json.loads((run/(row['request_id']+'.request.json')).read_text()) for arm,row in pair.items()}
        assert req['base']['messages']==req['lora']['messages']
        assert all(r['finish_reason']=='natural_stop' and r['output_token_ids'][-1] in (128001,128008,128009) for r in raw.values())
        note,flags=NOTES[key]
        output.append(dict(index=key[0],condition=key[1],note=note,flags=flags,
            input_identity=digest(req['base']['messages']),
            raw_identities={a:digest(r) for a,r in raw.items()},
            output_tokens={a:r['output_tokens'] for a,r in raw.items()},
            terminal_token_ids={a:r['output_token_ids'][-1] for a,r in raw.items()},
            independent_preference=None))
    result=dict(status='AI_DEVELOPMENT_OBSERVATIONS_NOT_REWARD_OR_HUMAN_EVAL',
        same_inputs_verified_pairs=len(output),natural_stop_calls=36,rows=output,
        tokens={a:dict(min=min(r['output_tokens'] for r in summary['rows'] if r['arm']==a),
            median=statistics.median(r['output_tokens'] for r in summary['rows'] if r['arm']==a),
            max=max(r['output_tokens'] for r in summary['rows'] if r['arm']==a)) for a in ('base','lora')},
        script_sha256=sha256_file(Path(__file__)),summary_sha256=sha256_file(run/'summary.json'),
        conclusion='NLL reduction and reload correctness do not establish adequate support/resource behavior. Engineering adapter remains unqualified.',
        limitation='Shorter alone is not a failure. These are concrete developer concerns, no pairwise winner labels or calibrated reward.')
    with (OUT/'diagnostic_observations_private.json').open('x') as f:f.write(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(pairs=len(output),tokens=result['tokens'])))
if __name__=='__main__':main()
