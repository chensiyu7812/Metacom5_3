#!/usr/bin/env python3
import argparse
import json
from metacom_pm.need_aware.data.personamem import prepare

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--source-root',required=True);p.add_argument('--output-root',required=True)
    a=p.parse_args();report=prepare(a.source_root,a.output_root)
    print(json.dumps({k:report[k] for k in ['selected','direct','history_files_parsed','train_val_persona_overlap','model_calls']},indent=2))
