"""Compare the untouched web probes and inspect AnnoMI annotation grain."""
import argparse
import csv
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path


def reconcile(source, behavior, annomi):
    a, b = json.loads(Path(source).read_text()), json.loads(Path(behavior).read_text())
    expected = {
        'evo.owners':18, 'evo.sessions':401, 'evo.legalSeekerNext':4119,
        'evo.qa.n':1427, 'evo.qa.groups':355, 'evo.qa.uniqueQuestionHashes':1420,
        'evo.resolution.emptyEvidence':260, 'evo.resolution.allResolved':1144,
        'evo.resolution.partiallyResolved':18, 'evo.resolution.noneResolved':5,
        'evo.resolution.multiSessionResolved':319, 'evo.resolution.strictPriorAll':80,
        'evo.resolution.hasSameOrLater':989,
        'evo.fullHistoryLexicalDiagnostic.top1Any':336,
        'evo.fullHistoryLexicalDiagnostic.top1All':256,
        'evo.fullHistoryLexicalDiagnostic.top4Any':684,
        'evo.fullHistoryLexicalDiagnostic.top4All':520,
        'annomi.rows':13551, 'annomi.transcripts':133, 'annomi.videoFamilies':119,
        'annomi.quality.high':110, 'annomi.quality.low':23,
        'annomi.roles.therapist':6826, 'annomi.eligibleContexts':4743,
        'annomi.highContexts':4331, 'annomi.priorChangeAndSustainProxy':288,
        'annomi.split.train':3932, 'annomi.split.test':811,
        'annomi.split.trainFamilies':96, 'annomi.split.testFamilies':23,
        'annomi.split.overlap':0, 'annomi.majority.correct':262,
        'annomi.legacy_context_overlap.correct':247,
        'annomi.legacy_case_overlap.correct':223,
        'annomi.client_context_cosine.correct':229,
    }
    checks=[]
    for key, value in expected.items():
        got=a
        for part in key.split('.'): got=got[part]
        checks.append(dict(field=key, expected=value, actual=got, match=got==value))
    for key, value in {'train':5992,'test':834,'trainGroups':96,'testGroups':23,'groupOverlap':0,
                       'majority.correct':267,'multinomial_nb.correct':629}.items():
        got=b
        for part in key.split('.'): got=got[part]
        checks.append(dict(field='behavior.'+key,expected=value,actual=got,match=got==value))
    for key,value in [('majority',.1213),('multinomial_nb',.7024)]:
        got=b[key]['macroF1']
        checks.append(dict(field='behavior.'+key+'.macroF1',expected_rounded=value,actual=got,match=round(got,4)==value))
    rows=list(csv.DictReader(Path(annomi).open()))
    grouped=defaultdict(list)
    for row in rows:grouped[(row['transcript_id'],row['utterance_id'])].append(row)
    conflicts=[]; conversations=defaultdict(list)
    for key,annotations in grouped.items():
        for field in ('utterance_text','interlocutor','video_url'):
            if len({r[field] for r in annotations})!=1:conflicts.append((key,field))
        conversations[key[0]].append(annotations[0])
    contexts=0;high=0
    for turns in conversations.values():
        turns.sort(key=lambda x:int(x['utterance_id']))
        for left,right in zip(turns,turns[1:]):
            if left['interlocutor']=='client' and right['interlocutor']=='therapist':
                contexts+=1;high+=right['mi_quality']=='high'
    therapist=[v for v in grouped.values() if v[0]['interlocutor']=='therapist']
    disagreements=sum(len({r['main_therapist_behaviour'] for r in v})>1 for v in therapist)
    ties=0
    for v in therapist:
        counts=Counter(r['main_therapist_behaviour'] for r in v).most_common()
        ties+=len(counts)>1 and counts[0][1]==counts[1][1]
    return dict(protocol='pmrl1-j-probe-reconciliation-v1',
        checks=checks, checks_passed=sum(c['match'] for c in checks), checks_total=len(checks),
        numeric_differences=[c for c in checks if not c['match']],
        grain=dict(annotation_rows=len(rows),unique_utterances=len(grouped),
            extra_annotation_rows=len(rows)-len(grouped),
            multiply_annotated_transcripts=len({k[0] for k,v in grouped.items() if len(v)>1}),
            unique_therapist_utterances=len(therapist),main_behavior_disagreement_utterances=disagreements,
            main_behavior_plurality_ties=ties,structural_conflicts=conflicts,
            unique_adjacent_client_therapist_positions=contexts,unique_high_positions=high),
        interpretation=['Original probe numbers reproduced; row-level label weighting is retained as development evidence.',
            'Original source-probe context text repeats multiply annotated utterances; corrected resources build unique utterance sequences.',
            'No generator benefit, clinical efficacy, reward qualification or new independent confirmation follows.'],
        inputs={str(p):hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in (source,behavior,annomi)})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--behavior',required=True);p.add_argument('--annomi',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();result=reconcile(a.source,a.behavior,a.annomi)
    with Path(a.output).open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('checks','inputs')},indent=2))
