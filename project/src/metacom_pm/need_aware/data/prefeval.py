"""Second-priority PrefEval loader; no generation or paid evaluator invocation."""
import json
from pathlib import Path
from .contracts import RuntimeTask,text_hash
from .history import HistoryResolver
from .personamem import write_json,write_jsonl,sha_file

REVISION='50795054b5ff5f418d2b768a331d71e480f93331'


def history_messages(row,kind):
    if kind=='explicit':
        # In this official condition preference IS the user-visible statement.
        return [{'role':'user','content':row['preference']}]
    if kind=='choice':
        return [{'role':'user' if key in {'query','user_selection'} else 'assistant','content':text}
                for key,text in row['conversation'].items()]
    if kind=='persona':
        return [{'role':role,'content':text} for turn in row['conversation'].values() for role,text in turn.items()]
    raise ValueError('unknown preference condition')


def prepare_prefeval(repo,out):
    repo,out=Path(repo),Path(out);root=repo/'benchmark_dataset'
    counts={};tasks=[];eval_rows=[];sources=[];families={}
    variants={'explicit':'explicit_preference','choice':'implicit_preference/choice-based','persona':'implicit_preference/persona-driven'}
    for kind,sub in variants.items():
        files=sorted((root/sub).glob('*.json'));total=0;exposed=0
        for file in files:
            rows=json.loads(file.read_text());total+=len(rows)
            sources.append({'path':str(file.relative_to(repo)),'sha256':sha_file(file),'rows':len(rows)})
            for i,row in enumerate(rows):
                family='prefeval-'+text_hash(file.stem+':'+str(i))[:20]
                families.setdefault(family,set()).add(kind)
                if exposed>=10:continue
                messages=history_messages(row,kind);ref=f'histories/{family}-{kind}.json'
                write_json(out/'runtime'/ref,{'owner_id':family,'source_family':family,'messages':messages})
                task=RuntimeTask(f'{family}-{kind}','prefeval:'+REVISION,'val',family,family,ref,
                                 sha_file(out/'runtime'/ref),len(messages),[],row['question'],'generation',[])
                HistoryResolver(out/'runtime').resolve(task)
                tasks.append(task.to_dict());eval_rows.append({'task_id':task.task_id,'gold_preference':row['preference'],
                    'scoring_protocol':'PrefEval official LLM evaluator not run','condition':kind})
                exposed+=1
        counts[kind]={'files':len(files),'rows':total,'cpu_samples':exposed}
    mcq_files=sorted((root/'mcq_options').glob('*.json'))
    mcq={f.name:len(json.loads(f.read_text())) for f in mcq_files}
    write_jsonl(out/'runtime/tasks.generation.jsonl',tasks);write_jsonl(out/'evaluation/tasks.jsonl',eval_rows)
    report={'revision':REVISION,'license':'CC-BY-NC-4.0','noncommercial_research_only':True,'variants':counts,
            'variant_family_count':len(families),'all_three_variants_shared_families':sum(len(v)==3 for v in families.values()),
            'real_independent_user_count':'not established; case families are not users',
            'official_split':'no train/val/test split in these benchmark topic files; local val denotes loader exposure only',
            'mcq_files':mcq,'mcq_raw_rows':sum(mcq.values()),'mcq_core_20_topics_rows':sum(n for f,n in mcq.items() if (root/'explicit_preference'/f).exists()),
            'runtime_samples':len(tasks),'model_calls':0,'official_generation_evaluator':'generation_task/llm_based_evaluation_errortypes.py (API; not called)',
            'official_mcq_entry':'classification_task/benchmark_classification.py; utils/utils_mcq.py (<choice>A</choice>, first source option is gold)',
            'source_files':sources}
    write_json(out/'receipt.json',report);return report
