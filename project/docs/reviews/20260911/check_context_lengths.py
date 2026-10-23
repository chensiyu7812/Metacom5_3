"""Read-only tokenizer compatibility preview; no weights, inference or ratings."""
import hashlib
import json
from pathlib import Path
import statistics
import sys

PROJECT = Path('/opt/tokkio-data0/tokkio_projects/Metacom5_3/project')
AUDIT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.paper1.evaluation.pairwise_teacher import build_pairwise_teacher_prompt
from transformers import AutoTokenizer

manifest_path = PROJECT / 'data/paper1_authority/paper1_pairwise_teacher_human_sheet_manifest_20260908_v2.json'
manifest = json.loads(manifest_path.read_text())
binding = manifest['sheets']['RATER_A']
blank = PROJECT / binding['path']
assert hashlib.sha256(blank.read_bytes()).hexdigest() == binding['sha256']
sheet = json.loads(blank.read_text())
assert all(i['verdict'] is None and i['rationale'] is None for i in sheet['items'])
models = json.loads((AUDIT / 'sources/candidate_metadata_summary.json').read_text())
selected = ['AtlaAI/Selene-1-Mini-Llama-3.1-8B', 'opencompass/CompassJudger-2-7B-Instruct', 'Unbabel/M-Prometheus-14B']
results = []
for model_id in selected:
    info = next(x for x in models if x['id'] == model_id)
    directory = AUDIT / 'sources' / (model_id.replace('/', '__') + '__tokenizer')
    tokenizer = AutoTokenizer.from_pretrained(directory, local_files_only=True)
    counts = []
    for item in sheet['items']:
        prompt = build_pairwise_teacher_prompt(task=item['task'], task_input=item['task_input'],
            response_a=item['response_A'], response_b=item['response_B'], reference_material=item['reference_material'])
        ids = tokenizer.apply_chat_template([{'role':'user', 'content':prompt}], tokenize=True, add_generation_prompt=True)
        counts.append({'presentation_id':item['presentation_id'], 'task':item['task'], 'input_tokens':len(ids)})
    maximum = max(x['input_tokens'] for x in counts)
    by_task = {}
    for task in ['ESC','QA','Summary','DG']:
        values = [x['input_tokens'] for x in counts if x['task'] == task]
        by_task[task] = {'n':len(values), 'min':min(values), 'median':statistics.median(values), 'max':max(values)}
    results.append({'model_id':model_id, 'revision':info['sha'],
        'config_context_limit':info['config']['max_position_embeddings'], 'max_input_tokens':maximum,
        'tokenizer_declared_max_length':tokenizer.model_max_length,
        'input_count_exceeding_tokenizer_declared_max':sum(x['input_tokens'] > tokenizer.model_max_length for x in counts),
        'draft_output_reserve_for_length_check_only':1024,
        'all_inputs_fit_model_config_with_draft_reserve':maximum + 1024 <= info['config']['max_position_embeddings'],
        'BF16_weights_only_GiB':round(info['params']['total']*2/1024**3,2),
        'by_task':by_task, 'rows':counts,
        'tokenizer_files_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir() if p.is_file()}})
result = {'status':'TOKENIZATION_PREVIEW_ONLY_NOT_JUDGE_QUALIFICATION',
    'prompt':'Existing Paper-1 common four-class prompt wrapped in each model chat template; NOT an approved candidate request identity.',
    'sheet_sha256':binding['sha256'], 'no_truncation':True,
    'runtime_or_long_context_accuracy_verified':False,
    'configuration_caveat':'Selene tokenizer declares 4096 while model config/model card declare 131072; Qwen tokenizers declare 131072 while these checkpoint configs declare 32768. Do not silently truncate or infer validated context ability from either field.',
    'output_reserve_note':'1024 is a length headroom illustration, not a proposed or changed generation cap.',
    'weights_downloaded':False, 'model_calls':0, 'real_ratings_created':0, 'candidates':results}
(AUDIT / 'context_length_preview.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({**result,'candidates':[{k:v for k,v in x.items() if k not in ['rows','tokenizer_files_sha256']} for x in results]},ensure_ascii=False,indent=2))
