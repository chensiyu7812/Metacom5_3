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

OUT = PROJECT/'outputs/pm_rl1/executor_pilot_20260929_v1'
MODEL = Path('/opt/tokkio-data0/tokkio_models/huggingface/hub/models--NousResearch--Meta-Llama-3.1-8B-Instruct/snapshots/d10aef7999a2b5ba950ab3974312feeedbfe0b77')

# Explicit pre-outcome development judgments; R does NOT mean positive utility.
CHOICES = [
 ('MS','ME','Earlier studies/relationship/time-boundary discussion is relevant; current breakup overrides former hope.','Club follow-up intentions are not the current overload/breakup concern.'),
 ('RS','ME','An open invitation fits the unspecified immediate wish to talk.','Past consultation of friends/family does not establish today\'s topic.'),
 ('ME','RS','Earlier supervisor interactions contextualize the current ongoing work conflict.','Interview anxiety is not stated; user only plans light exploration.'),
 ('RS','MP','Ask about the rough week before guessing its cause.','Interest in anxiety techniques does not establish anxiety or a request for techniques now.'),
 ('MP','ME','The parent/older-son relationship can disambiguate Jerry without overriding current return.','Past longing for Jerry\'s return has been superseded by the explicit return.'),
 ('MS','MP','Past breakup anxiety and reflective coping are related context, not current facts.','Having a close friend need not be imported into the encounter described now.'),
 ('ME','RS','Earlier uncertainty about the breakup matches the expressed unresolved questions.','Direct conversation may conflict with the current choice to process this in therapy first.'),
 ('MS','MP','Earlier job search and considered recruiter options may contextualize limited alternatives.','Quick trust in people is not evidence relevant to relocation/pay tradeoffs.'),
 ('RS','ME','Invitation/permission to elaborate fits the unspecified rough day.','Prior alcohol-help discussion does not establish the current topic.'),
 ('RS','MP','A greeting can be answered with an open invitation.','Religious involvement is not invited by the current greeting.'),
 ('MS','ME','Earlier parental university pressure explains the currently mentioned argument.','Earlier bullying by friends does not establish the present source of distraction.'),
 ('RS','MP','An invitation to share fits a vague request to talk.','Past panic history does not establish a present attack or warrant a clinical framing.'),
 ('ME','RS','Past repeated talks with parents can contextualize autonomy conflict; do not assume same issue.','Friends are not the current interlocutor in the conflict with mother.'),
 ('ME','RS','Past thesis criticism is related and largely redundant; reply should respect closure.','Personal scholarship self-disclosure is ungrounded for this assistant and mismatches rejection.'),
 ('MS','RS','Earlier therapy/boundary experience is related; do not conflate romantic colleague and college friend.','Staying busy conflicts with the current wish to limit commitments.'),
 ('MS','MP','Earlier caregiving and possible shared responsibility offer related historical context.','Sleep difficulty is not in the selected source conversation; audit as unverified, never assert it.'),
 ('RS','MP','A question about existing support may help contextualize requested workplace advice.','Sleep difficulty does not address favoritism and is unverified in selected source conversation.'),
 ('MS','MP','Past harassment and fear of repercussions contextualize current leadership concerns.','Supportive listening to a friend is a different relationship/context.'),
]

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
    contract = dict(version='r05-pilot-admission-v1', reviewer='Codex coordinator AI-assisted development review',
        independent_human_truth=False, old_q_m_used=False, repairs=0,
        statuses=['accept','reject','uncertain','technical_failure'],
        checks=['natural nonempty completion','exact visible input and reply identities','no additional hidden/future facts',
                'speaker/entity and time grounding including presuppositions','current request and boundaries',
                'no invented assistant personal experience','avoid forcing unsuitable resources','useful appropriate next turn'],
        quality_note='Source support does not alone prove appropriate support. Suggestions and uncertain possibilities are not automatically factual claims.',
        resource_note='R means related candidate, not proven incremental utility; L may be redundant, outdated or topic-mismatched. Labels are never given to author.',
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
    with (OUT/'condition_contract_private.json').open('x') as f:
        f.write(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(conditions=len(rows), planned_author_calls=108, contract_sha256=sha256_file(OUT/'condition_contract_private.json'))))

if __name__ == '__main__': main()
