#!/usr/bin/env python3
"""Linux runtime reader sandbox. Deliberately exposes no evaluation/source data."""
import argparse
from pathlib import Path
import subprocess

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--runtime-root',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    here=Path(__file__).resolve();source=here.parents[2]/'src';out=Path(a.output).resolve();out.mkdir(parents=True,exist_ok=True)
    command=['bwrap','--die-with-parent','--new-session','--unshare-all','--clearenv',
             '--ro-bind','/usr','/usr','--ro-bind','/lib','/lib','--ro-bind','/lib64','/lib64',
             '--proc','/proc','--dev','/dev','--tmpfs','/tmp',
             '--ro-bind',str(source),'/src','--ro-bind',str(here.with_name('cpu_runtime_receipt.py')),'/entry.py',
             '--ro-bind',str(Path(a.runtime_root).resolve()),'/runtime','--bind',str(out),'/output',
             '--setenv','PYTHONPATH','/src','--setenv','PYTHONDONTWRITEBYTECODE','1',
             '--setenv','LANG','C.UTF-8','/usr/bin/python3','/entry.py']
    subprocess.run(command,check=True)
