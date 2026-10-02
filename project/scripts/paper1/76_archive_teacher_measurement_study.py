#!/usr/bin/env python3
"""Export a descriptive, source-bound figure/table for the judge study."""
from pathlib import Path
import csv
import hashlib
import json

PROJECT = Path(__file__).resolve().parents[2]
ROOT = PROJECT / 'docs/reviews/20260917'


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':9,'svg.fonttype':'none','pdf.fonttype':42})
    cpath = ROOT / 'local_teacher_comparison_statistics.json'
    spath = ROOT / 'local_teacher_summary_evidence_statistics.json'
    comparison = json.loads(cpath.read_text())['candidates']
    evidence = json.loads(spath.read_text())['candidates']
    natural = json.loads((ROOT/'summary_natural_end_statistics.json').read_text())['by_arm']
    names = [('qwen35_9b','Qwen3.5-9B'),('compassjudger2_7b','CompassJudger-2'),('selene_reasoning_first','Selene reasoning-first'),('selene_mini_8b','Selene JSON')]
    rows = []
    for key,name in names:
        c=comparison[key]; n=c['format_normalized_sensitivity'];o=n['order'];v=n['views']['original_A']['four_class']['base_pairs']
        rows.append({'configuration':name,'strict_valid':c['statuses'].get('SUCCEEDED',0),
                     'format_normalized_usable':n['usable_presentations'],'scheduled':160,
                     'order_consistent':o['consistent'],'order_comparable':o['paired_bases'],
                     'missing_order_pairs':o['missing_pairs'],'human_A_matches':v['exact_matches'],
                     'human_A_comparable':v['observed'],'human_A_agreement_is_accuracy':False})
    with (ROOT/'judge_measurement_table.csv').open('w',newline='',encoding='utf-8-sig') as h:
        w=csv.DictWriter(h,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    fig,axes=plt.subplots(1,3,figsize=(13.8,4.4),gridspec_kw={'width_ratios':[1.1,1.3,1]})
    colors=['#186a83','#698f55','#ba8040','#9099a2']
    for i,row in enumerate(rows):
        pct=100*row['order_consistent']/row['order_comparable']
        axes[0].barh(i,pct,color=colors[i]);axes[0].text(pct+1,i,f"{row['order_consistent']}/{row['order_comparable']}",va='center',fontsize=8)
    axes[0].set_yticks(range(4),[n for _,n in names]);axes[0].invert_yaxis();axes[0].set_xlim(0,110)
    axes[0].set_title('A  Order consistency: 80 base pairs');axes[0].set_xlabel('Consistent decisions (%)')
    labels=['Short reference','Full history','Full history + natural end']
    for j,(key,name) in enumerate(names[:3]):
        before=comparison[key]['format_normalized_sensitivity']['order_by_task']['Summary']
        points=[before,*[evidence[key]['variants'][v]['order'] for v in ['same_answers_full_history','natural_answers_full_history']]]
        for i,p in enumerate(points):
            x=i+(j-1)*.23;y=100*p['consistent']/p['paired_bases']
            axes[1].bar(x,y,width=.22,color=colors[j],label=name if i==0 else None)
            axes[1].text(x,y+1.5,f"{p['consistent']}/{p['paired_bases']}",ha='center',fontsize=7)
    axes[1].set_xticks(range(3),['Short\nreference','Full\nhistory','Full history +\nnatural end']);axes[1].set_ylim(0,114)
    axes[1].set_title('B  Summary: 13 fixed base pairs');axes[1].set_ylabel('Order consistency (%)');axes[1].legend(loc='upper center',bbox_to_anchor=(.5,-.2),fontsize=7,frameon=False)
    for i,label in enumerate(['ON','OFF']):
        old = natural[label]['old_length_stops']
        assert natural[label]['new_natural_stops'] == natural[label]['requests'] == 13
        axes[2].bar(i-.16,old,width=.3,color='#ba8040',label='Original length stop' if i==0 else None)
        axes[2].bar(i+.16,0,width=.3,color='#186a83',label='After natural-end generation' if i==0 else None)
        axes[2].text(i-.16,old+.25,str(old),ha='center');axes[2].text(i+.16,.25,'0',ha='center')
    axes[2].set_xticks([0,1],['ON (13)','OFF (13)']);axes[2].set_ylim(0,13);axes[2].set_title('C  Summary output completeness');axes[2].set_ylabel('Length-stopped responses');axes[2].legend(loc='upper center',bbox_to_anchor=(.5,-.2),fontsize=7,frameon=False)
    for ax in axes:
        ax.spines[['top','right']].set_visible(False);ax.set_axisbelow(True)
    fig.text(.01,.025,'Descriptive development comparison. Order consistency is not accuracy; denominators exclude missing decisions. Evidence and decoding conditions are documented.',fontsize=8)
    fig.subplots_adjust(left=.145,right=.99,wspace=.37,bottom=.29,top=.87)
    for ext in ['png','svg','pdf']:fig.savefig(ROOT/f'judge_measurement_figure.{ext}',dpi=220)
    sources={str(p.relative_to(PROJECT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [cpath,spath,ROOT/'summary_natural_end_statistics.json']}
    (ROOT/'judge_measurement_figure_manifest.json').write_text(json.dumps({'kind':'exploratory_measurement_analysis','new_model_calls':0,'source_sha256':sources,'rows':rows},ensure_ascii=False,indent=2)+'\n')
    print('Figure PNG/SVG/PDF, table and source manifest saved.')


if __name__=='__main__':main()
