#!/usr/bin/env python3
"""Reuse the frozen V1 engine under a separate format-v2 input/output root."""
import argparse
import importlib.util
from pathlib import Path

HERE=Path(__file__).resolve().parent


def main(preflight_only):
    spec=importlib.util.spec_from_file_location('p2_local_engine',HERE/'82_run_p2_local_jobs.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.OUT=module.OUT/'review_format_v2'
    module.main('review',preflight_only)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--preflight-only',action='store_true');main(p.parse_args().preflight_only)
