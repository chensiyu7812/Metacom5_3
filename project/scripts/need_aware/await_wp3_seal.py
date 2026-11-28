#!/usr/bin/env python3
"""One bounded CPU completion subscriber; no device/process/log monitoring."""
import argparse,json,os,time
from pathlib import Path
from types import SimpleNamespace
from finalize_wp3 import run
from metacom_pm.need_aware.data.contracts import digest
from metacom_pm.need_aware.data.personamem import write_json,sha_file


def main(a):
    os.umask(0o077);start=time.monotonic();marker=Path(a.marker)
    while not marker.exists():
        if time.monotonic()-start>a.wait_seconds:raise TimeoutError('no sealed WP3 completion event before subscriber deadline')
        time.sleep(300)
    event=json.loads(marker.read_text());md=Path(a.manifest_dir)
    if Path(event['manifest']).resolve()!=md.resolve():raise ValueError('unexpected manifest path')
    manifest=json.loads((md/'MANIFEST.json').read_text())
    if digest(manifest)!=a.manifest_sha256:raise ValueError('unexpected manifest identity')
    run(a)
    write_json(Path(a.handoff),dict(protocol='naa-a-w3-scored-v1',result_kind='real_model',
        manifest_sha256=a.manifest_sha256,postprocess_complete=str(Path(a.out)/'POSTPROCESS_COMPLETE.json'),
        confirm=str(Path(a.out)/'CONFIRM_AGGREGATE.json'),bridge=str(Path(a.out)/'BRIDGE_AGGREGATE.json'),
        completion_sha256=sha_file(Path(a.out)/'POSTPROCESS_COMPLETE.json'),
        next_step='A/B interpret predeclared comparisons and agree deployable supply; no automatic condition/authorization change'))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ('marker','manifest-dir','manifest-sha256','ledger-root','wp3','policy','old-scored','out','handoff'):
        p.add_argument('--'+n,required=True)
    p.add_argument('--wait-seconds',type=int,default=21600)
    a=p.parse_args()
    try:main(a)
    except Exception as exc:
        write_json(Path(a.handoff).with_name('A_W3_SCORING_FAILED.json'),
            dict(type=type(exc).__name__,message=str(exc),artifacts_preserved=True,gpu_calls=0))
        raise
