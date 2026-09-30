#!/usr/bin/env python3
"""Freeze reviewed coverage inputs, actual GET paths, and finite next-stage work.

Source judgments are explicit coordinator review, not an automatic entailment
test or human gold. No generation, gradient update or reward labeling here.
"""
from collections import Counter
from dataclasses import asdict
import html
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.io import sha256_file
from metacom_pm.paper1.data.memory_source import load_sanitized_runtime_users
from metacom_pm.paper1.llama_tokenizer import build_llama_token_counter
from metacom_pm.rl1.evidence import prefix_from_dict
from metacom_pm.rl1.render import Renderer
from metacom_pm.rl1.resource_plan_preflight import validate_resource_plans
from metacom_pm.rl1.schema import EpisodeSpec, HEADS, Resource, digest

OUT = PROJECT / 'outputs/pm_rl1/executor_coverage_20260929_v1'
PACK = OUT / 'qualified_inputs'
OLD = PROJECT / 'outputs/pm_rl1/executor_pilot_20260929_v2'
ENGINEERING = PROJECT / 'outputs/pm_rl1/executor_engineering_20260929_v1'
MODEL = Path('/opt/tokkio-data0/tokkio_models/huggingface/hub/models--NousResearch--Meta-Llama-3.1-8B-Instruct/snapshots/d10aef7999a2b5ba950ab3974312feeedbfe0b77')

# Review of the complete current prefix and each selected source, before any
# new replies. These notes are private, never appended to author/G inputs.
NOTES = {
2: dict(tags=['irrelevant_profile', 'open_invitation'], RS='Invite the user to explain the present concern.',
    MP='The office-worker fact is explicit in esc81 turn 4. No present work topic is given; do not guess one from this profile.'),
12: dict(tags=['self_report_not_diagnosis', 'multiple_resources'],
    MP='esc1216 turn 6 explicitly self-reports learning difficulties. This is not a clinical diagnosis; preserve that scope.',
    MS='Complete p11_conv_4: Lily moving, grades, pressure, reluctance to approach teachers. Reading again was contemplated, not completed coping success.',
    RS='Online groups are an authentic suggestion but add little to the current academic/family request.'),
18: dict(tags=['irrelevant_profile', 'open_invitation'], RS='Respond to the greeting without presuming a problem.',
    MP='esc894 turn 19 supports a photography interest and owning a camera. It does not establish regular practice or the topic of this hello.'),
26: dict(tags=['entity_separation', 'historical_support'],
    ME='esc410 turns 21/22 report feeling understood by another pet owner. This supports a past support experience, not resolution of grief or proof David helps now.',
    MP='esc410 turns 13/15/18 support loving dogs. Do not identify the earlier deceased female dog as the current Max. This profile is mostly redundant.'),
35: dict(tags=['current_corroboration', 'multiple_resources'],
    MP='p16_conv_4 explicitly documents repeated dismissals by the supervisor; the current negative review corroborates the ongoing relationship difficulty.',
    ME='The esc371 event is supported by the full source: stress/burnout in turn 3, persistence in 5, supervisor talking over the user in 7, workload/unheard in 10. Not a durable medical condition.',
    RS='An authentic senior-complaint suggestion; current fear of retaliation limits its appropriateness. No obligation to recommend reporting.'),
42: dict(tags=['historical_community_preference', 'exclusion_context'],
    MS='Complete esc67 records two exclusions and friends saying they forgot. Current confrontation and mixed reactions supply the later state.',
    MP='esc629 turns 17/19 support religious identification, past youth-group experience and interest in support. They do not show present group membership or a successful intervention.'),
50: dict(tags=['irrelevant_profile', 'open_invitation'], RS='Invite the user to speak; the current request has no topic yet.',
    MP='esc611 turns 14/16 explicitly prefer directness in the ex-relationship. Do not generalize it to all domains or assume that relationship is today\'s topic.'),
61: dict(tags=['entity_separation', 'multiple_resources', 'redundancy'],
    MS='Complete p3_conv_2 concerns repairing a friendship with Henry. Current reconnection is with an ex-girlfriend; the people and relationship outcomes must remain distinct.',
    ME='p3_conv_2 turns 20/22 support relief from that conversation. It overlaps the MS and does not prove the current romantic relationship is repaired.',
    RS='Talking about feelings is a possible move. The current couple already reconnected; do not rewrite this as a merely future first contact.'),
67: dict(tags=['financial_constraint', 'multiple_resources', 'selective_use'],
    MP='esc652 turn 16 explicitly says therapy is unaffordable. Current financial strain makes cost relevant, without turning the old report into a new permanent confirmation.',
    MS='Complete p5_conv_1: daughter\'s health, doctor guidance, reported mutual breaks and running. Distinguish actually reported benefit from future suggestions.',
    RS='Part-time work is an authentic strategy but may add burden here. The mixed set deliberately permits ignoring this component.',
    ME='p5_conv_1 turns 8/22 support talking helping. Valid but redundant with the supplied MS/current conversation; no required benefit.'),
79: dict(tags=['current_limits_old_benefit', 'multiple_resources'],
    MP='p6_conv_15 turn 15 reports journaling helps/feels therapeutic. Current input explicitly limits this benefit and says it does not change the job situation; respect that update.',
    ME='p6_conv_16 turn 15 supports relief about staying and fear of stagnation. It does not say the promotion was awarded; current non-promotion governs.',
    RS='Presence/reassurance is an authentic generic move, not evidence of changed work circumstances.'),
85: dict(tags=['intention_not_action', 'multiple_resources'],
    MS='Complete p8_conv_7 records a gathering relapse and Bob\'s support. It is distinct from quarantined esc995 role-play; do not revive the denied workplace drinking claim.',
    ME='p8_conv_7 turn 14 supports considering boundaries/mediation, not actually completing mediation. Current partial mindfulness benefit and professional-help interest take precedence.',
    RS='A brief walk is optional and low in specificity for the present professional-help opening.'),
91: dict(tags=['advice_not_action', 'redundancy'],
    MS='Complete esc682: online search had started; career/recruiter help was suggested and not yet tried. Never claim outreach occurred or caused improvement.',
    ME='esc682 turn 5 explicitly states online searching. Source-valid and repeated in the current prefix.'),
98: dict(tags=['workplace_temporal_update', 'multiple_resources'],
    MS='Complete p1_conv_1 concerns harassment, contemplated HR contact and retaliation fears. Current boss resignation is later; do not assume HR intervention already happened.',
    RS='A different job is a possible topic, not an established user intention or compulsory solution.',
    MP='p1_conv_4 turn 17 explicitly values listening with boundaries for a friend. This is separate from the workplace problem and may be ignored.'),
101: dict(tags=['friend_not_self', 'privacy', 'multiple_resources'],
    MS='Complete p1_conv_4 supports therapy/boundaries and yoga/reading. The blog request is current; do not prescribe publishing private dating/friend details.',
    ME='p1_conv_3 turn 7 describes a friend opening up about the friend\'s mental health. Do not change the experiencer to the user.',
    RS='The archived fear-of-weakness reflection is optional; do not assert that exact fear when the current user only describes vulnerability/relatability.'),
103: dict(tags=['assistant_personal_story', 'episode_separation'],
    MS='Complete esc1138 concerns parents opposing a trip with a boyfriend. The current friends-choice conflict is another episode. The current assistant\'s mother story is not a license to invent personal experience.',
    RS='Talking to friends is an authentic option but not the same as the present mother conflict. The assistant should not continue its earlier invented autobiography.'),
105: dict(tags=['plan_to_action_update', 'multiple_resources'],
    MS='Complete p15_conv_1: thesis criticism and friend contact only contemplated then. Current old-college-friend messaging actually occurred; do not erase that change.',
    ME='Complete p15_conv_7 confirms support/conversation helped, including turn 22 optimism. Other gestures in that session remained intentions.',
    RS='Generic well-wishing/help-seeking may be acceptable and need not lose to the R condition.'),
112: dict(tags=['support_person_scope', 'multiple_resources'],
    MP='p18_conv_2 turns 7/8 establish sister Annie and the user\'s confirmation of her support. Not proof she can solve workplace favoritism.',
    RS='Discussing with others is a possible move; do not infer an effective workplace intervention from family support.',
    ME='p18_conv_2 turn 20 confirms feeling less alone during caregiving. It does not describe this workplace issue.'),
113: dict(tags=['care_plan_not_result', 'multiple_resources'],
    MP='Annie is source-supported in p18_conv_2 and current input corroborates her help and strain. Do not assume her capacity is unlimited.',
    MS='Complete p18_conv_1: burden and possible sibling redistribution/walks. Current trying to divide responsibilities is not completed, balanced care.',
    RS='Asking whether it is too much is largely redundant with the explicit current account.'),
}


def read(path):
    return json.loads(path.read_text())


def save(name, value):
    path = PACK / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as f:
        f.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def make_renderer():
    from transformers import AutoConfig, AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
    return Renderer(count_text=build_llama_token_counter(MODEL / 'tokenizer.json'),
        count_chat=lambda m: len(tokenizer.apply_chat_template(m, tokenize=True, add_generation_prompt=True)),
        tokenizer_identity=digest(dict(tokenizer=sha256_file(MODEL / 'tokenizer.json'), template=tokenizer.chat_template)),
        context_limit=AutoConfig.from_pretrained(MODEL, local_files_only=True).max_position_embeddings)


def load_specs(raws):
    return [EpisodeSpec(**dict(raw, prefix=prefix_from_dict(raw['prefix']),
        inventory=tuple(tuple(Resource(**dict(r, source_ids=tuple(r['source_ids']))) for r in rows)
                        for rows in raw['inventory']))) for raw in raws]


def main():
    prep = read(OUT / 'preparation_manifest.json')
    for name, expected in prep['files'].items():
        assert sha256_file(OUT / name) == expected, name
    for name, expected in prep['source_hashes'].items():
        assert sha256_file(PROJECT / name) == expected, name
    renderer = make_renderer()
    assert renderer.identity == prep['renderer_identity']
    choices = read(OUT / 'coverage_selection_draft.json')
    # Raw context makes the 'favorite child' MP ambiguous (possibly sarcasm).
    # Record exclusion rather than certifying it merely to increase MP count.
    next(c for c in choices if c['census_index'] == 103)['related'] = [0, 0, 1, 0]
    indices = [c['census_index'] for c in choices]
    raw_specs = [read(OUT / 'episode_specs_private.json')[i - 1] for i in indices]
    specs = load_specs(raw_specs)
    evidence = [dict(read(OUT / 'legal_evidence_private.json')[i - 1], index=j)
                for j, i in enumerate(indices, 1)]
    maps = [read(OUT / 'coordinator_only/evidence_source_map.json')[i - 1] for i in indices]
    units_path = PROJECT / 'data/paper1_public_memory/es_memeval_public_multi_view_session_results_v1.jsonl'
    units = {u['memory_id']: u for line in units_path.read_text().splitlines() for u in json.loads(line)['accepted_units']}
    users = {u.owner_id: u for u in load_sanitized_runtime_users(
        PROJECT / 'data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json')}
    conditions, reviews, cases = [], [], []
    for index, (choice, spec, erow, mapping) in enumerate(zip(choices, specs, evidence, maps), 1):
        ci = choice['census_index']
        notes = NOTES[ci]
        cases.append(dict(index=index, census_index=ci, owner=spec.prefix.owner_id, split=spec.prefix.split,
            prefix_identity=spec.prefix.identity, tags=notes['tags'], private_review=notes))
        selected = {}
        for label, counts in [('OFF', (0, 0, 0, 0)), ('R', tuple(choice['related'])), ('L', tuple(choice['low']))]:
            assert renderer.fits(spec, counts), (ci, label, renderer.cost(spec, counts))
            resources = [asdict(r) for rows, n in zip(spec.inventory, counts) for r in rows[:n]]
            selected.update({r['candidate_id']: r for r in resources})
            messages = renderer.messages(spec, counts)
            conditions.append(dict(index=index, census_index=ci, prefix_identity=spec.prefix.identity,
                owner=spec.prefix.owner_id, split=spec.prefix.split, condition=label, counts=counts,
                resource_tokens=renderer.cost(spec, counts), messages=messages, messages_identity=digest(messages),
                resource_ids=[r['candidate_id'] for r in resources]))
        session_map = {s['session']: s for s in mapping['source_map']}
        blind_map = {s['id']: s for s in erow['evidence']['legal_past_sessions']}
        for r in selected.values():
            if r['head'] == 'RS':
                refs = [dict(kind='strategy', candidate_id=r['candidate_id'], source_ids=r['source_ids'],
                             content_identity=digest(r['content']))]
            else:
                unit = units[r['source_ids'][0]] if r['head'] in ('MP', 'ME') else None
                sid = unit['source_session_id'] if unit else r['source_ids'][0]
                source = users[spec.prefix.owner_id].session_by_id(sid)
                assert source.chronological_rank < spec.prefix.cutoff_rank
                session = blind_map[session_map[sid]['blind_id']]
                assert [t['text'] for t in session['turns']] == [t.content for t in source.turns]
                base_ref = dict(session_id=session['id'], session_identity=digest(session), source_session=sid)
                refs = []
                if unit:
                    span_by_turn = {s['turn_index']: s['exact_text'] for s in unit['supporting_spans']}
                    extras = [5, 7, 10] if ci == 35 and r['head'] == 'ME' else [7, 8] if ci in (112, 113) and r['head'] == 'MP' else []
                    for pos, turn in enumerate(source.turns):
                        if turn.idx in span_by_turn or turn.idx in extras:
                            quote = span_by_turn.get(turn.idx, turn.content)
                            assert quote in turn.content
                            refs.append(dict(**base_ref, kind='turn', turn_id=session['turns'][pos]['id'],
                                source_turn_index=turn.idx, role=turn.role, quote=quote))
                    assert len(refs) >= len(span_by_turn)
                    assert unit['rendered_candidate_content'] == r['content']
                else:
                    refs = [dict(**base_ref, kind='complete_session', scope='complete raw transcript, roles and dates inspected')]
            reviews.append(dict(candidate_id=r['candidate_id'], prefix_identity=spec.prefix.identity,
                resource_identity=digest(r), evidence_identity=erow['evidence_identity'],
                status='source_supported', temporal_status_checked=True,
                reviewer='Codex coordinator AI-assisted complete-prefix/source-context review', independent_human_gold=False,
                rationale=notes[r['head']], evidence_refs=refs,
                limitation='Selected claim/source only; not certification of all inventory entries or downstream output assertions.'))

    save('episode_specs_private.json', raw_specs)
    save('legal_evidence_private.json', evidence)
    save('source_reviews_private.json', reviews)
    save('casebook_private.json', cases)
    save('selection_private.json', dict(choices=choices, rationale='Source-grounded coverage supplement to the prior admitted dataset; no new outcome has been observed.',
        prior_outcomes_known=True, test_prefixes=0, full_corpus_certified=False,
        excluded=[dict(census_index=103, candidate_id='mp::mvu_cafa3f541134140a7d9d0ea6',
            reason='favorite-child remark may be sarcastic in the complete parental-control source; literal MP uncertain, omitted without fallback/re-ranking')]))

    old_contract = read(OLD / 'condition_contract_private.json')
    old_run = Path(read(OLD / 'author_pointer.json')['run_dir'])
    old_lookup = {}
    for j in read(old_run / 'jobs.json'):
        request_path = old_run / (j['request_id'] + '.request.json')
        request = read(request_path)
        key = (j['prefix_identity'], digest(request['messages']), j['seed'])
        assert key not in old_lookup
        raw_path = old_run / (j['request_id'] + '.raw.json')
        old_lookup[key] = dict(origin_request_id=j['request_id'], request_path=str(request_path), raw_path=str(raw_path),
            request_sha256=sha256_file(request_path), raw_sha256=sha256_file(raw_path),
            rule='Reuse original output AND original admission status; not a new independent draw or a chance to reverse rejection.')
    author_jobs = []
    for c in conditions:
        for seed in old_contract['seeds']:
            key = (c['prefix_identity'], c['messages_identity'], seed)
            reuse = old_lookup.get(key)
            author_jobs.append(dict(index=c['index'], condition=c['condition'], split=c['split'],
                prefix_identity=c['prefix_identity'], messages_identity=c['messages_identity'], seed=seed,
                action='reuse_existing' if reuse else 'generate_once', provenance=reuse))
    counts = Counter(j['action'] for j in author_jobs)
    save('author_work_manifest.json', dict(jobs=author_jobs, counts=dict(counts),
        old_author_runtime_sha256=sha256_file(old_run / 'runtime.json'),
        old_admission_reviews_sha256=sha256_file(OLD / 'admission_reviews_private.json'),
        purpose='Reuse all exact prior inputs/seeds, including failed/uncertain replies. Generate only previously unseen input/seed pairs.'))
    guards = [OUT / 'preparation_manifest.json', OUT / 'coverage_selection_draft.json',
        OLD / 'condition_contract_private.json', OLD / 'admission_reviews_private.json',
        ENGINEERING / 'accepted_dataset_private.json', old_run / 'runtime.json',
        PROJECT / 'src/metacom_pm/rl1/resource_plan_preflight.py', PROJECT / 'src/metacom_pm/rl1/source_quarantine.py',
        PROJECT / 'src/metacom_pm/rl1/env.py', PROJECT / 'src/metacom_pm/rl1/render.py', Path(__file__)]
    guards += [OUT / name for name in prep['files']] + [PROJECT / name for name in prep['source_hashes']]
    guards += [PACK / name for name in ('episode_specs_private.json', 'legal_evidence_private.json',
        'source_reviews_private.json', 'casebook_private.json', 'selection_private.json', 'author_work_manifest.json')]
    contract = dict(version='r05-source-qualified-coverage-supplement-v1', status='INPUTS_FROZEN_BEFORE_NEW_OUTPUTS',
        renderer_identity=renderer.identity, conditions=conditions, seeds=old_contract['seeds'], author=old_contract['author'],
        source_guard={str(p.relative_to(PROJECT)): sha256_file(p) for p in guards},
        admission=dict(statuses=['accept', 'reject', 'uncertain', 'technical_failure'], repairs=0,
            checks=old_contract['admission']['checks'], reviewer='AI-assisted weak-supervision review, not independent human truth',
            reply_rule='Admit only individually source-grounded, appropriate, naturally completed replies. Preserve failures; no minimum length or required memory mention.',
            semantic_review='Record current-request adequacy, claims with exact visible-input support, selective use/ignore, and temporal/entity/assistant-persona errors separately.',
            coverage_rule='Report accepted examples by head, owner, single/multiple resources and reviewed use/ignore/current-update. No per-cell all-pass or required historical-uptake success count.',
            structural_scope='Accepted training must actually cover all four heads and mixed-resource inputs for a four-head executor claim. Zero coverage limits the claim; it does not license relabeling or automatic redraw.',
            outcomes='No requirement for ON to beat OFF, X_l to beat X_g, or every R/L cell to contain an accepted reply. Missing cells remain visible.'),
        training=dict(**old_contract['training'], initialization='Original frozen Llama base plus fresh LoRA; do not continue the engineering adapter',
            dataset='Union of the old 90 accepted originals and new accepted replies; exact prompt/response duplicates included once; old rejected/uncertain rows remain excluded.',
            split='Existing owner split only; reused dev is development data, never confirmatory test.',
            nll='Report all/body/EOT token losses separately; retain response+EOT optimization and the original NLL checkpoint rule.',
            generation_diagnostics='Fixed six selected dev prefixes x OFF/R/L x base/epochs1/2/3 = 72 natural-end replies; no checkpoint selection from these qualitative outcomes.',
            stop_rule='One finite supplement and one predeclared three-epoch run; no automatic extension to obtain positive benefit. Any further source-coverage expansion is separately versioned before test, within the original 96-extra-prefix ceiling.'),
        boundaries=dict(paid_api_calls=0, new_human_forms=0, natural_support_ppo=False, test_access=False,
            old_all_cell_gate_result='FAILED unchanged; this is a distinct coverage contract with prospective rules, not a retroactive pass',
            reward_qualification='Pending R04B finite measurement study; source review/admission is not a reward judge'),
        author_work_counts=dict(counts), diagnostic_calls=72)
    receipt = validate_resource_plans(contract, specs=specs, evidence=evidence, reviews=reviews, renderer=renderer)
    save('condition_contract_private.json', contract)
    save('generation_preflight.json', receipt)
    stats = {}
    for split in ('train', 'dev'):
        group = [c for c in conditions if c['split'] == split]
        stats[split] = dict(prefixes=len(group) // 3, owners=len({c['owner'] for c in group}), conditions=len(group),
            resource_occurrences=sum(sum(c['counts']) for c in group),
            head_condition_counts={h: sum(c['counts'][i] > 0 for c in group) for i, h in enumerate(HEADS)},
            mp_owners=len({c['owner'] for c in group if c['counts'][1]}),
            mixed_resource_conditions=sum(sum(c['counts']) > 1 for c in group),
            maximum_resource_tokens=max(c['resource_tokens'] for c in group))
    save('coverage_summary.json', dict(status='QUALIFIED_INPUTS_ONLY_OUTPUT_ADMISSION_AND_TRAINING_PENDING',
        counts=stats, source_reviews=len(reviews), author_work_counts=dict(counts),
        admitted_new_replies=0, new_parameter_updates=0, API_usd=0,
        limitation='Input provision is not learned usage or incremental quality. Source semantic review is AI-assisted, selected-case only.'))
    cards = []
    for case in cases:
        cs = [c for c in conditions if c['index'] == case['index']]
        revs = [r for r in reviews if r['prefix_identity'] == case['prefix_identity']]
        cards.append('<section><h2>' + html.escape(f"{case['index']:02d} / census {case['census_index']} · {case['owner']} · {case['split']}") + '</h2>'
            + '<p>' + html.escape(' / '.join(case['tags'])) + '</p>'
            + ''.join('<details><summary>' + html.escape(f"{c['condition']} {tuple(c['counts'])} · {c['resource_tokens']} resource tokens")
                + '</summary><pre>' + html.escape(json.dumps(c['messages'], ensure_ascii=False, indent=2)) + '</pre></details>' for c in cs)
            + '<details><summary>Private source review and exact references (never model input)</summary><pre>'
            + html.escape(json.dumps(revs, ensure_ascii=False, indent=2)) + '</pre></details></section>')
    page = '<!doctype html><html lang="zh"><meta charset="utf-8"><title>PM-RL1 来源与覆盖输入包</title>'
    page += '<style>body{max-width:1100px;margin:32px auto;padding:0 20px;font:16px/1.6 system-ui;background:#f6f7f9;color:#182230}section{background:white;padding:18px;margin:18px 0;border:1px solid #ccd5df;border-radius:8px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}summary{cursor:pointer;padding:8px}h1{font-size:26px}</style>'
    page += '<h1>PM-RL1 来源与覆盖输入包</h1><p>18 个开发前缀、54 个条件。此页是已核对输入与来源的浏览页，不是新人工问卷、输出评分或完整语料认证。R/L 为私下选材描述，不表示收益正负。模型仅看到展开的精确 messages。</p>'
    page += '<pre>' + html.escape(json.dumps(stats, ensure_ascii=False, indent=2)) + '</pre>' + ''.join(cards) + '</html>'
    with (PACK / 'review.html').open('x') as f:
        f.write(page)
    save('freeze_manifest.json', dict(status='PRE_GENERATION_INPUT_FREEZE',
        files={str(p.relative_to(PACK)): sha256_file(p) for p in sorted(PACK.rglob('*')) if p.is_file()},
        contract_identity=digest(contract), preflight_identity=digest(receipt),
        source_semantic_review='AI-assisted selected-source development review; not independent human gold'))
    print(json.dumps(dict(counts=stats, reviews=len(reviews), author_work=dict(counts), status='FROZEN'), ensure_ascii=False))


if __name__ == '__main__':
    main()
