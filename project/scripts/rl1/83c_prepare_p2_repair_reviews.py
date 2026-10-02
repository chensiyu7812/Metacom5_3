#!/usr/bin/env python3
"""Apply the same single format clarification to the bounded repaired targets."""
import importlib.util
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
OUT=PROJECT/'outputs/pm_rl1/completion_20260930_v2/P2'


def main():
    spec=importlib.util.spec_from_file_location('p2_prepare_reviews',Path(__file__).with_name('83_prepare_p2_reviews.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    prompt=json.loads((OUT/'review_format_v2/supervision_protocol.json').read_text())['review_prompt']
    original=m.review_messages
    def messages(slot,response,docs):
        result=original(slot,response,docs);result[0]['content']=prompt;return result
    m.review_messages=messages;m.REVIEW_INSTRUCTION=prompt
    m.main(True)
    # Complete this newly created freeze before any call, binding the wrapper.
    path=OUT/'review_repair_jobs_freeze.json';freeze=json.loads(path.read_text())
    for p in (Path(__file__),OUT/'review_format_v2/supervision_protocol.json'):
        freeze['files'][str(p.relative_to(PROJECT))]=sha256_file(p)
    freeze['format']='Exact same format-v2 instruction; no further prompt revision'
    path.write_text(json.dumps(freeze,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
