"""Public GPU visibility guard; preserves the prior A6000 admission rules.

No model loading, process termination or device fallback. Empty visible process
lists are a scoped observation, never proof of host-wide exclusivity.
"""
import csv
import io
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
from .supervised_learning import save_json

def parse_gpu(gpu, compute, xml, expected_uuid, own_pid=None):
    reasons=[];selected=None;visible=[];visibility='unknown'
    try:
        rows=list(csv.reader(io.StringIO(gpu)))
        matches=[r for r in rows if r and r[0].strip()==expected_uuid]
        if len(matches)!=1:raise ValueError('designated UUID missing or duplicated')
        r=[x.strip() for x in matches[0]]
        if len(r)!=4:raise ValueError('GPU CSV field count')
        selected=dict(uuid=r[0],name=r[1],free_mib=int(r[2]),utilization_percent=int(r[3]))
        if selected['free_mib']<0 or not 0<=selected['utilization_percent']<=100:raise ValueError('GPU value range')
        if 'A6000' not in r[1]:reasons.append('designated_uuid_product_mismatch')
    except (ValueError,TypeError) as exc:reasons.append('gpu_query_parse_error: '+str(exc))
    try:
        doc=ET.fromstring(xml)
        matches=[g for g in doc.findall('gpu') if g.findtext('uuid')==expected_uuid]
        if len(matches)!=1:raise ValueError('XML designated UUID missing or duplicated')
        g=matches[0];processes=g.find('processes')
        if processes is None or (processes.text or '').strip() not in ('','None'):
            raise ValueError('XML processes unavailable')
        for p in processes.findall('process_info'):
            pid=int(p.findtext('pid'));name=p.findtext('process_name');kind=p.findtext('type')
            if pid<=0 or not name or name in ('N/A','[Not Found]') or not kind:
                raise ValueError('process metadata unavailable')
            visible.append(dict(pid=pid,name=name,type=kind,source='nvidia-smi XML'))
        csv_pids=[]
        for row in csv.reader(io.StringIO(compute)):
            if not row:continue
            if len(row)!=4:raise ValueError('compute CSV field count')
            if row[0].strip()!=expected_uuid:raise ValueError('compute query UUID mismatch')
            pid=int(row[1].strip());name=row[2].strip()
            if pid<=0 or not name or name in ('N/A','[Not Found]'):raise ValueError('compute process metadata unavailable')
            csv_pids.append(pid)
            if not any(p['pid']==pid for p in visible):
                visible.append(dict(pid=pid,name=name,type='C',source='nvidia-smi compute CSV'))
        visibility='queries_succeeded_visible_processes' if visible else 'queries_succeeded_no_processes_listed'
        if any(p['pid']!=own_pid for p in visible):reasons.append('other_visible_gpu_process')
    except (ValueError,TypeError,ET.ParseError) as exc:reasons.append('process_visibility_unknown: '+str(exc))
    if selected is not None and own_pid is None:
        if selected['free_mib']<45000:reasons.append('free_memory_below_45000_MiB')
        if selected['utilization_percent']!=0:reasons.append('utilization_not_zero')
    return dict(selected_gpu=selected,visible_processes=visible,process_visibility=visibility,
        visibility_limit='Successful empty process lists describe what these NVIDIA queries expose; they do not prove absence of hidden, transient or future jobs.',
        rejection_reasons=reasons,eligible=not reasons,
        guard='original free>=45000MiB and util==0 plus visible-process check' if own_pid is None else 'resident model: original other-process exclusion; no idle threshold applied to our own loaded model')


class LocalGPUCheck:
    def __init__(self, expected_uuid, runtime, root):
        self.uuid,self.runtime,self.root=expected_uuid,runtime,Path(root)
        self.root.mkdir(parents=True,exist_ok=True)

    def check(self, *, own_pid=None):
        if (os.environ.get('CUDA_VISIBLE_DEVICES')!=self.runtime['cuda_visible_devices']
                or os.environ.get('CUDA_DEVICE_ORDER')!=self.runtime['cuda_device_order']):
            raise ValueError('frozen CUDA deployment changed')
        mapping=subprocess.run(['nvidia-smi','--query-gpu=pci.bus_id,uuid','--format=csv,noheader'],
            capture_output=True,text=True,timeout=20)
        rows=sorted([x.strip() for x in line.split(',')] for line in mapping.stdout.splitlines())
        ordinal=int(self.runtime['cuda_visible_devices'])
        if (mapping.returncode or ordinal<0 or len(rows)<=ordinal or any(len(r)!=2 for r in rows)
                or rows[ordinal][1]!=self.uuid):
            raise ValueError('GPU ordinal/UUID mismatch')
        commands=[['nvidia-smi','-i',self.uuid,'--query-gpu=uuid,name,memory.free,utilization.gpu','--format=csv,noheader,nounits'],
            ['nvidia-smi','-i',self.uuid,'--query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory','--format=csv,noheader,nounits'],
            ['nvidia-smi','-i',self.uuid,'-q','-x']]
        queries=[]
        for cmd in commands:
            r=subprocess.run(cmd,capture_output=True,text=True,timeout=20)
            queries.append(dict(argv=cmd,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr))
        result=parse_gpu(*(r['stdout'] for r in queries),expected_uuid=self.uuid,own_pid=own_pid)
        if any(r['returncode'] for r in queries):result['rejection_reasons'].append('GPU query failed')
        try:
            mounts=[x for x in Path('/proc/mounts').read_text().splitlines() if x.split()[1]=='/proc']
            if any('hidepid=1' in x or 'hidepid=2' in x for x in mounts):
                result['rejection_reasons'].append('process_visibility_restricted_hidepid')
            if os.readlink('/proc/self/ns/pid')!=os.readlink('/proc/1/ns/pid'):
                result['rejection_reasons'].append('process_visibility_namespace_mismatch')
        except OSError:
            result['proc_context']='unavailable; NVIDIA visibility remains scoped'
        result.update(eligible=not result['rejection_reasons'],queries=queries,
            mapping=dict(returncode=mapping.returncode,stdout=mapping.stdout,stderr=mapping.stderr))
        index=len(list(self.root.glob('check_*.json')))
        save_json(self.root/f'check_{index:04d}.json',result)
        if not result['eligible']:raise RuntimeError('designated GPU unavailable; no waiting, termination or fallback')
        return result
