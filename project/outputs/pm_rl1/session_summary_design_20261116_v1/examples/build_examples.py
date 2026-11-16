#!/usr/bin/env python3
"""Serialize assistant-authored session-summary design examples; no model calls.

The author read each entire selected session. This script binds authored claims to
unchanged source turns. It is not an automatic summarizer or semantic validator.
"""
from pathlib import Path
import hashlib
import json

OUT = Path(__file__).resolve().parent
SOURCE = OUT.parents[1] / 'research_preparation_20261115_v1/memory/SELECTED_COMPLETE_SESSIONS_PRIVATE.json'

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()

# Each sentence carries source turn ordinals; original raw turn namespaces must
# not be silently substituted for these exported ordinals.
AUTHORED = {
 'M04': {
  'theme': 'Self-worth, academic pressure, writing and social support',
  'sentences': [
   ('The seeker felt overwhelmed and described a recent therapy conversation about tying self-worth to academic and creative success; recognizing this brought relief as well as anxiety about changing it.', [1,3,5,7], 'events_and_turning_points', 'reported_experience'),
   ('University workload still felt heavy, with a continuing sense of not doing enough.', [9], 'unresolved_matters', 'reported_current_at_session'),
   ('They had joined a writing workshop and reported that it helped, while impostor feelings still recurred.', [11], 'attempts_and_reported_reactions', 'attempt_plus_subjective_response'),
   ('They said knowing they were not alone helped and separately described an online community as supportive, reminding them that struggle and gradual growth were acceptable.', [13,15], 'attempts_and_reported_reactions', 'subjective_response_and_support_context'),
   ('The supporter mainly validated these difficulties and offered encouragement; the seeker appreciated being listened to and intended to take things one step at a time and catch up again.', [6,8,12,16,17,19,20], 'support_and_next_steps', 'supporter_behavior_plus_seeker_intention'),
  ],
  'explicit_preferences_or_constraints': [],
  'not_established': ['No specific size or duration of workshop benefit was reported.', 'The intention to proceed gradually is not a completed action or recovery.', 'No persistent response preference or stable personality trait is inferred.'],
  'self_review': ['Keeps mixed relief and anxiety rather than reducing the therapy conversation to improvement.', 'Keeps workshop benefit and residual difficulty together.', 'Does not assign the benefit of feeling less alone specifically to an online-community intervention.', 'Includes the closing intention rather than ending at the old MP/ME quote.'],
 },
 'M17': {
  'theme': 'Maintaining a friendship while handling dominating, lengthy conversations',
  'sentences': [
   ('The seeker was frustrated by a long-standing friend whose phone conversations could run for hours; when an early reflection confused whose frustration was involved, the seeker clarified that the friend enjoyed talking and the seeker disliked it.', [2,3,4,5,15], 'events_and_turning_points', 'reported_problem_plus_conversational_correction'),
   ('They had repeatedly asked the friend to stop, share speaking time and respect others\' time, but reported the pattern recurring; they had also hung up, and said the friend became easily offended.', [7,8,11,13], 'attempts_and_reported_reactions', 'attempt_plus_subjective_response'),
   ('They still wanted the friendship, valuing the friend\'s humor, perspectives and shared history, and explicitly wanted a practical method because talking about the problem had not worked.', [15,18,22], 'explicit_preferences_or_constraints', 'session_specific_goal_and_request'),
   ('A timer softened with humor was discussed as an idea, followed by the supporter\'s suggestions to occupy the hands or attention; none was reported as newly tried during the session.', [20,24,25,28,30,32,34,35,37,38], 'support_and_next_steps', 'discussed_options_not_completed_actions'),
   ('The seeker explicitly said they did not really like drawing and considered using the internet on their phone instead.', [33,35,36], 'explicit_preferences_or_constraints', 'explicit_preference_plus_intention'),
   ('At the close, they said the ideas addressed the in-person situation but did not solve the telephone conversations, while describing this conversation as helpful and the supporter as kind.', [38,39], 'unresolved_matters', 'subjective_appraisal_with_unresolved_problem'),
  ],
  'not_established': ['A timer, distraction or internet use was not observed to improve later conversations.', 'The seeker\'s closing appraisal is not evidence that the phone problem was solved.', 'The supporter\'s own claimed family experience is not the seeker\'s history and is not transferred into this summary as user experience.', 'Disliking drawing in this session is not generalized to disliking all creative activities.'],
  'self_review': ['Preserves the correction about who is frustrated.', 'Does not repeat the old error that the seeker simply avoids hanging up.', 'Retains both the wish to preserve the friendship and the request for a practical method.', 'Preserves the unresolved phone-versus-in-person distinction despite positive closing feedback.', 'Does not endorse treating or conditioning a friend; records the conversational options as proposals.'],
 },
 'M24': {
  'theme': 'Work appraisal, self-doubt, relationships and a helpful creative outlet',
  'sentences': [
   ('The seeker was disappointed by the previous day\'s performance review: their boss called the work adequate, which led them to question whether they were doing a good job.', [2,4,6], 'events_and_turning_points', 'reported_event_and_response'),
   ('They linked being on edge to an unspecified past incident with an old boss, worried about a friend and not burdening them, and hoped the distress would not affect their relationship with Jack, which had had ups and downs.', [8,10,12], 'unresolved_matters', 'reported_concerns_with_missing_details'),
   ('The supporter validated the disappointment, separated the appraisal from personal worth, encouraged attending to the seeker\'s own needs and suggested communicating feelings.', [5,7,11,13], 'support_and_next_steps', 'supporter_suggestions_not_user_facts'),
   ('The seeker intended to talk to Jack that night and said that being open seemed helpful in their relationship; the planned conversation itself had not yet occurred in the account.', [14], 'support_and_next_steps', 'intention_separate_from_subjective_appraisal'),
   ('When asked about the painting hobby, the seeker said it helped as a creative outlet, even for a short time.', [15,16], 'attempts_and_reported_reactions', 'context_bound_subjective_response'),
   ('They appreciated the listening and encouragement and intended to take things one step at a time; the session did not report a later work or relationship outcome.', [18,19,20,21], 'unresolved_matters', 'closing_appraisal_and_intention'),
  ],
  'explicit_preferences_or_constraints': [],
  'not_established': ['The past incident with the old boss is not described here; its nature is unknown.', 'The friend\'s situation is unspecified.', 'The supporter\'s statement that Jack cares is not independently confirmed by the seeker in this session.', 'The conversation with Jack is a plan, not a successful completed intervention.', 'Painting benefit is subjective and is not a claim of long-term recovery.'],
  'self_review': ['Resolves It does help using the immediately preceding painting question.', 'Does not invent details of the old boss incident or the friend\'s problem.', 'Separates the subjective appraisal of openness from the intended conversation that night; does not infer a specific past trial or established outcome.', 'Preserves work concern and relationship concern rather than keeping only the coping action.'],
 },
}

sessions = {s['sample_id']: s for s in json.loads(SOURCE.read_text())}
counts = []
for sample_id, authored in AUTHORED.items():
    s = sessions[sample_id]
    assert s['split'] in ('train', 'dev')
    assert digest(s['source']) == s['normalized_source_sha256']
    claims, sentences, sections = [], [], {}
    for n, (text, indices, section, epistemic_status) in enumerate(authored['sentences'], 1):
        claim_id = f'{sample_id}:C{n:02d}'
        evidence = []
        for index in indices:
            turn = s['source']['turns'][index]
            evidence.append({'turn_ordinal': index, 'speaker': turn['role'], 'start_char': 0,
                             'end_char': len(turn['text']), 'quote': turn['text']})
        claims.append({'claim_id': claim_id, 'text': text, 'epistemic_status': epistemic_status,
                       'source_sha256': s['normalized_source_sha256'], 'evidence': evidence,
                       'reviewed_complete_session': True})
        sentences.append({'text': text, 'claim_ids': [claim_id]})
        sections.setdefault(section, []).append(claim_id)
    summary_text = ' '.join(x['text'] for x in sentences)
    raw_words = sum(len(t['text'].split()) for t in s['source']['turns'])
    summary_words = len(summary_text.split())
    candidate = {
      'schema': 'pmrl1-completed-session-summary-design-example-v1',
      'sample_id': sample_id,
      'status': 'ASSISTANT_AUTHORED_SCHEMA_PROTOTYPE_NOT_AUTOMATIC_SUMMARIZER_RESULT',
      'source': {'owner_id': s['source']['owner_id'], 'session_id': s['source']['session_id'],
                 'split': s['split'], 'reported_at': s['source']['reported_at'],
                 'session_rank': s['source']['session_rank'],
                 'normalized_source_sha256': s['normalized_source_sha256'],
                 'turn_count': len(s['source']['turns']), 'full_source_file': f'{sample_id}_source.json'},
      'availability': {'requires_session_complete': True, 'usable_only_in_later_sessions': True,
                       'source_session_itself_forbidden': True,
                       'availability_time_exact': None,
                       'notion': 'post-session artifact; use source order and completion, not date alone',
                       'existing_legal_later_prefix_bindings': s['legal_prefix_bindings']},
      'construction': {'author': 'Codex assistant', 'input_scope': 'entire one completed source session only',
                       'constructed_on_client_date': '2026-11-16',
                       'retrospective_design_example': True,
                       'historically_created_at_session_end': False,
                       'future_session_inputs': False, 'target_query_inputs': False,
                       'external_model_or_API_calls': 0, 'independent_review': 'pending',
                       'query_independent': True, 'summary_of_previous_summaries': False,
                       'production_integration': False},
      'theme': authored['theme'],
      'summary_text': summary_text,
      'summary_sentences': sentences,
      'structured_claim_index': sections,
      'explicit_preferences_if_not_identified': authored.get('explicit_preferences_or_constraints'),
      'not_established': authored['not_established'],
      'claim_source_ledger': claims,
      'quality_self_review': authored['self_review'],
      'measurement': {'raw_text_whitespace_words': raw_words,
                      'summary_text_whitespace_words': summary_words,
                      'summary_to_raw_word_ratio': summary_words / raw_words,
                      'counts_exclude_metadata_and_source_ledger': True,
                      'token_counts': None, 'latency_measurements': None,
                      'G_helpfulness_measured': False},
      'limits': ['Assistant-authored schema examples do not measure a deployable summarizer.',
                 'Mechanical span checks do not establish semantic completeness.',
                 'Full raw source is retained; this summary does not replace historical MS identities.',
                 'Audit source ledger is not automatically part of the G payload.',
                 'No source claim is promoted to a stable MP fact without separate time-aware validation.'],
    }
    (OUT/f'{sample_id}_source.json').write_text(json.dumps(s['source'], ensure_ascii=False, indent=2)+'\n')
    (OUT/f'{sample_id}_summary_candidate.json').write_text(json.dumps(candidate, ensure_ascii=False, indent=2)+'\n')
    counts.append({'sample_id': sample_id, 'source_words': raw_words, 'summary_words': summary_words,
                   'claims': len(claims), 'source_spans': sum(len(c['evidence']) for c in claims)})

validation = {'status': 'PASS_EXACT_SOURCE_HASH_AND_SPAN_BINDING', 'samples': counts,
              'independent_semantic_validation': 'pending', 'formal_runtime_approval': False,
              'automatic_summarizer_evaluation': False, 'helpfulness_gain_measured': False,
              'note': 'Every full session was read by one assistant. Unstated facts remain unknown.'}
for entry in counts:
    candidate = json.loads((OUT/f'{entry["sample_id"]}_summary_candidate.json').read_text())
    source = json.loads((OUT/f'{entry["sample_id"]}_source.json').read_text())
    assert digest(source) == candidate['source']['normalized_source_sha256']
    for claim in candidate['claim_source_ledger']:
        for ev in claim['evidence']:
            turn = source['turns'][ev['turn_ordinal']]
            assert turn['role'] == ev['speaker']
            assert turn['text'][ev['start_char']:ev['end_char']] == ev['quote']
(OUT/'VALIDATION.json').write_text(json.dumps(validation, ensure_ascii=False, indent=2)+'\n')
print(json.dumps(validation, ensure_ascii=False, indent=2))
