#!/usr/bin/env python3
"""Bind pre-generation condition audit and exact visible author inputs."""
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import EpisodeSpec, Resource, HEADS, digest
from metacom_pm.rl1.evidence import prefix_from_dict
from metacom_pm.rl1.render import Renderer
from metacom_pm.paper1.llama_tokenizer import build_llama_token_counter
from transformers import AutoTokenizer, AutoConfig

OUT = PROJECT/'outputs/pm_rl1/executor_pilot_20260929_v2'
MODEL = Path('/opt/tokkio-data0/tokkio_models/huggingface/hub/models--NousResearch--Meta-Llama-3.1-8B-Instruct/snapshots/d10aef7999a2b5ba950ab3974312feeedbfe0b77')

# Explicit pre-outcome development judgments; R does NOT mean positive utility.
CHOICES = [('MS', 'ME', 'Past Jerry-school episode includes reported therapy breathing/communication; keep Jerry distinct from George.', 'Earlier work/family support is factual but adds little to the present bullying concern.'), ('MS', 'RS', 'Past boyfriend discussion documents concern about giving up personal goals; current parents/art question still takes precedence.', 'Archived human self-disclosure strategy is authentic; an assistant cannot claim that personal life.'), ('RS', 'ME', 'Ask about present overwhelm before guessing its cause.', 'Earlier breakup/friends episode is source-supported but does not establish the present work problem.'), ('ME', 'RS', 'Prior gratitude for shared understanding may help with accepting support; do not identify the earlier female dog as Max.', 'Dog-shelter advice is a real strategy, but current concern is accepting David support rather than seeking dog activities.'), ('ME', 'MS', 'Past contemplated breakup contextualizes current completed decision; current breakup supersedes the old intention.', 'Memorial/family reconnection is a separate past episode; not proof of current breakup support.'), ('MS', 'ME', 'Earlier exclusion from two events explains prior hurt; current confrontation supplies the latest state.', 'Professors and friends are separate relationships; earlier academic complaint must not be transferred.'), ('MS', 'ME', 'Prior midterm failure and planned writing break are historical context for academic distress, not accomplished coping success.', 'Earlier friends/family discussion concerned an ex, not this classmate or project.'), ('MS', 'ME', 'Henry friendship repair offers a distinct past communication example; never identify Henry as the ex-girlfriend.', 'Past relief from talking about Henry is largely generic support evidence, not proof of present romantic resolution.'), ('MS', 'RS', 'Past mutual breaks and morning running are explicit coping reports; current financial argument remains unresolved.', 'Part-time-work suggestion is an archived option, not an established need or the immediate request about supporting Margaret.'), ('MS', 'ME', 'Past review, loss of Lisa contact and journaling contextualize current self-doubt; no current friendship revival.', 'Past relief from conversation is true but low in specific information about current job choice.'), ('MS', 'RS', 'Past sharing at a gathering explains hurt and notes one friend tried; avoid all-friends-never-care generalization.', 'Location disclosure is an archived strategy with no basis for inventing an assistant residence.'), ('MS', 'ME', 'Earlier job search and considered counselor/recruiter advice are relevant; outreach and success were not completed.', 'Earlier online search is true and repeated in the current prefix; little additional information.'), ('MS', 'ME', 'Earlier therapy/boundary reports are historical context; do not assume unnamed earlier friend is Mark.', 'Past request for support during work overwhelm is source-supported but mostly redundant.'), ('MS', 'ME', 'Past self-expression, boundaries and yoga/reading are available examples; personal dating history need not be disclosed in the blog.', 'Past private conversation with friend is real, but not consent to publish that friend story.'), ('MS', 'RS', 'Earlier thesis criticism is a separate academic setback; present group-project dismissal should not be conflated with it.', 'Human workplace self-disclosure strategy is authentic but does not license invented assistant personal experience.'), ('MS', 'RS', 'Prior thesis setback supplies historical contrast; current college-friend contact is actual, not merely planned.', 'Generic reassurance/help-seeking is a valid low-information strategy; it need not be harmful or lose.'), ('MS', 'ME', 'Earlier shared-care discussion and planned walks are historical context; current sister conversation does not prove redistribution occurred.', 'Past caring for mother is corroborated by full source and current input but redundant.'), ('RS', 'MP', 'Ask about discussion/support while respecting request for workplace advice.', 'Sister Annie support is confirmed by immediately preceding session; irrelevant to proving workplace favoritism, and no claim she can solve it.')]

def main():
    tokenizer = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
    renderer = Renderer(count_text=build_llama_token_counter(MODEL/'tokenizer.json'),
        count_chat=lambda m: len(tokenizer.apply_chat_template(m, tokenize=True, add_generation_prompt=True)),
        tokenizer_identity=digest(dict(tokenizer=sha256_file(MODEL/'tokenizer.json'), template=tokenizer.chat_template)),
        context_limit=AutoConfig.from_pretrained(MODEL, local_files_only=True).max_position_embeddings)
    prep = json.loads((OUT/'preparation_manifest.json').read_text())
    for name, expected in prep['files'].items():
        assert sha256_file(OUT/name) == expected, name
    assert renderer.identity == prep['renderer_identity']
    raw_specs = json.loads((OUT/'episode_specs_private.json').read_text())
    rows = []
    for index, (raw, choice) in enumerate(zip(raw_specs, CHOICES), 1):
        spec = EpisodeSpec(**dict(raw, prefix=prefix_from_dict(raw['prefix']),
            inventory=tuple(tuple(Resource(**dict(r, source_ids=tuple(r['source_ids']))) for r in group) for group in raw['inventory'])))
        related, low, rr, lr = choice
        for condition, head, rationale in [('OFF',None,'No retrieved resources.'),('R',related,rr),('L',low,lr)]:
            counts = tuple(int(h == head) for h in HEADS)
            assert renderer.fits(spec, counts)
            messages = renderer.messages(spec, counts)
            rows.append(dict(index=index, prefix_identity=spec.prefix.identity, owner=spec.prefix.owner_id,
                split=spec.prefix.split, condition=condition, head=head, counts=counts,
                resource_tokens=renderer.cost(spec,counts), messages=messages, messages_identity=digest(messages),
                rationale=rationale, source_ids=[] if head is None else spec.inventory[HEADS.index(head)][0].source_ids))
    from dataclasses import asdict
    evidence=json.loads((OUT/'legal_evidence_private.json').read_text())
    options=json.loads((OUT/'condition_options_private.json').read_text())
    units={u['memory_id']:u for line in (PROJECT/'data/paper1_public_memory/es_memeval_public_multi_view_session_results_v1.jsonl').read_text().splitlines() for u in json.loads(line)['accepted_units']}
    source_reviews=[]
    for c in rows:
        if c['head'] is None:continue
        resource=next(o['resource'] for o in options[c['index']-1]['options'] if o['head']==c['head'])
        if c['head'] in ('MP','ME'):
            u=units[resource['source_ids'][0]]
            refs=[dict(session=u['source_session_id'],turn=s['turn_index'],quote=s['exact_text']) for s in u['supporting_spans']]
            # Full-session context inspected as well as compiled atom excerpts.
            extras={7:[17,18,20],13:[1,3,19],17:[5,7,9],18:[7,8]}
            refs += [dict(session=u['source_session_id'],context_turn=t) for t in extras.get(c['index'],[])]
        elif c['head']=='MS':refs=[dict(session=resource['source_ids'][0],scope='complete source transcript read; speaker roles preserved')]
        else:refs=[dict(canonical_strategy=resource['candidate_id'],source_ids=resource['source_ids'],scope='frozen strategy source; recommendation rather than user fact')]
        source_reviews.append(dict(candidate_id=resource['candidate_id'],prefix_identity=c['prefix_identity'],
            resource_identity=digest(resource),evidence_identity=evidence[c['index']-1]['evidence_identity'],
            status='source_supported',temporal_status_checked=True,
            reviewer='Codex coordinator AI-assisted source/current-input review',independent_human_gold=False,
            rationale=c['rationale'],evidence_refs=refs,
            limitation='Checks the supplied claim/transcript and relevant timing, not every unselected historical claim or all downstream output assertions.'))
    review_path=OUT/'source_reviews_private.json'
    with review_path.open('x') as f:f.write(json.dumps(source_reviews,ensure_ascii=False,indent=2)+'\n')
    guarded=[PROJECT/'outputs/pm_rl1/source_repair_20260929_v2/source_overlay_private.json',
        PROJECT/'src/metacom_pm/rl1/source_repair.py',PROJECT/'src/metacom_pm/rl1/source_preflight.py',
        PROJECT/'src/metacom_pm/rl1/source_quarantine.py',PROJECT/'scripts/rl1/47_author_repaired_pilot.py',
        PROJECT/'scripts/rl1/38_author_executor_pilot.py',review_path,OUT/'preparation_manifest.json']
    guarded += [PROJECT/k for k in prep['source_hashes']]
    guarded += [OUT/k for k in prep['files']]
    guard={str(p.relative_to(PROJECT)):sha256_file(p) for p in guarded}
    contract = dict(version='r05-pilot-admission-v2', reviewer='Codex coordinator AI-assisted development review',
        independent_human_truth=False, old_q_m_used=False, repairs=0,
        statuses=['accept','reject','uncertain','technical_failure'],
        checks=['natural nonempty completion','exact visible input and reply identities','no additional hidden/future facts',
                'speaker/entity and time grounding including presuppositions','current request and boundaries',
                'no invented assistant personal experience','avoid forcing unsuitable resources','useful appropriate next turn'],
        quality_note='Source support does not alone prove appropriate support. Suggestions and uncertain possibilities are not automatically factual claims.',
        resource_note='R means related candidate, not proven incremental utility; L is source-supported but may be redundant, superseded or topic-mismatched; it is not required to be harmful. Labels are never given to author.',
        coverage_gate='At least one accepted response per train/dev prefix-condition; at least four train prefixes with explicitly reviewed historical resource uptake. Otherwise stop before training.',
        uncertainty='Reject or uncertain is retained with rationale, never automatically repaired or rescored.',
        target='Only accepted original author response plus EOT. No reviews, full private history, q/m, original future replies or test data.')
    obj = dict(status='FROZEN_BEFORE_AUTHOR_GENERATION', input_preparation_sha256=sha256_file(OUT/'preparation_manifest.json'),
        renderer_identity=renderer.identity, seeds=[17,29], conditions=rows, admission=contract,
        author=dict(model='/opt/tokkio-data0/tokkio_models/paper1_judges/qwen35_9b', thinking=False,
            purpose='example author only, not a reward judge', visible_input='exact Renderer.messages only',
            temperature=.7, top_p=.8, top_k=20, min_p=0., presence_penalty=1.5, repetition_penalty=1.,
            output_cap=None, stopping='native EOS/EOT; native context remainder; 300s technical timeout; 32-token cycle repeated 4 times',
            official_decode_reference='https://huggingface.co/Qwen/Qwen3.5-9B'),
        training=dict(lora_r=8,lora_alpha=16,target_modules=['q_proj','v_proj'],dropout=0.,dtype='bfloat16',
            lr=1e-4,microbatch=1,accumulation=16,epochs=3,seed=17,optimizer='AdamW, betas .9/.999, eps 1e-8, weight_decay 0',
            gradient_clip_norm=1., loss='response+EOT token mean over each accumulation group, including last partial group',
            checkpoint_choice='minimum token-weighted response dev NLL across epochs 1..3; report baseline separately',
            reload_nll_absolute_tolerance=1e-4),
        author_calls=108,diagnostic_calls=36,paid_api_calls=0,source_code_sha256=sha256_file(Path(__file__)))
    obj['source_guard']=guard
    obj['source_review_note']='36 explicit AI-assisted source/current-prefix reviews completed before author generation; this is not human gold or full-corpus validation.'
    with (OUT/'condition_contract_private.json').open('x') as f:
        f.write(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(conditions=len(rows), planned_author_calls=108, contract_sha256=sha256_file(OUT/'condition_contract_private.json'))))

if __name__ == '__main__': main()
