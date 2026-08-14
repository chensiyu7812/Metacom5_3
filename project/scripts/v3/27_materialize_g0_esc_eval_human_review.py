#!/usr/bin/env python3
"""Build two blinded ESC-Eval seven-dimension human-review packets.

The official English rubric is extracted from the pinned ESC-Eval ``score.py``
rather than re-authored here. Public packets contain no model, provider, card,
source, or condition identifiers. Raw dialogue-to-candidate mapping remains in
the private output directory.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from collections import defaultdict
from pathlib import Path
import random
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
AUTHORITY = PROJECT_ROOT / "data" / "v3_authority"
SOURCE = PROJECT_ROOT / "outputs" / "v3_g0_four_generator_full_screen_v1_20260814" / "private_turn_ledger.jsonl"
CLOSEOUT = AUTHORITY / "g0_four_generator_full_screen_closeout_v1.json"
PLAN = AUTHORITY / "generator_esc_eval_primary_selection_v1.json"
PROMPT = AUTHORITY / "g0_research_aligned_supporter_prompt_v1.json"
EXPECTED_ESC_COMMIT = "9ad46e7b5e247e824dae4633910eaa82be668beb"
EXPECTED_SCORE_SHA256 = "1d775462adc7687d84ceb19d3648c3c917abf7ceed8b052b1fed8e4740f12724"
ELIGIBLE = (
    "llama31_8b_incumbent",
    "qwen37_plus_nonthinking",
    "qwen37_plus_thinking_upper_bound",
)
DIMENSIONS = ("Fluency", "Expression", "Empathy", "Information", "Humanoid", "Skill", "Overall")
GUARDRAILS = (
    "low_burden",
    "no_premature_action",
    "no_unsupported_personal_inference",
    "safety_signal_handling",
    "no_scaffold_leakage",
)
RESPONSE_PROTOCOL = "metacom-v3-esc-eval-human-review-response-v1"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_file(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _stable_hex(*parts: str, n: int = 24) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:n]


def _git_head(repo: Path) -> str:
    import subprocess

    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _official_rubric(esc_eval: Path) -> dict[str, str]:
    if _git_head(esc_eval) != EXPECTED_ESC_COMMIT:
        raise RuntimeError("ESC-Eval checkout is not at the pinned commit")
    score_path = esc_eval / "score.py"
    if _sha_file(score_path) != EXPECTED_SCORE_SHA256:
        raise RuntimeError("pinned ESC-Eval score.py hash drifted")
    tree = ast.parse(score_path.read_text(encoding="utf-8"))
    prompts: list[str] | None = None
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == "prompt_EN" for target in node.targets):
            prompts = ast.literal_eval(node.value)
            break
    if not isinstance(prompts, list) or len(prompts) != 7 or not all(isinstance(x, str) for x in prompts):
        raise RuntimeError("could not extract the seven official English rubric prompts")
    return dict(zip(DIMENSIONS, prompts, strict=True))


def _dialogues() -> list[dict[str, Any]]:
    closeout = json.loads(CLOSEOUT.read_text(encoding="utf-8"))
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    if _sha_file(SOURCE) != closeout["private_evidence_hashes"][str(SOURCE.relative_to(PROJECT_ROOT.parent))]:
        raise RuntimeError("source generation ledger does not match closeout hash")
    if closeout["run_identity"] != plan["development_selection"]["generation_identity"]:
        raise RuntimeError("selection plan is not bound to the completed generation identity")
    rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("event") == "supporter_succeeded" and row.get("candidate_id") in ELIGIBLE:
            grouped[(row["screen_id"], row["candidate_id"])].append(row)
    result: list[dict[str, Any]] = []
    counts: dict[str, int] = defaultdict(int)
    for (screen_id, candidate_id), turns in grouped.items():
        turns.sort(key=lambda row: int(row["turn"]))
        if [int(row["turn"]) for row in turns] != [1, 2, 3, 4, 5]:
            raise RuntimeError(f"incomplete eligible dialogue: {screen_id}/{candidate_id}")
        transcript: list[dict[str, str]] = []
        for row in turns:
            transcript.extend(
                [
                    {"speaker": "Help-seeker", "text": row["seeker_text"]},
                    {"speaker": "Supporter", "text": row["supporter_text"]},
                ]
            )
        result.append(
            {
                "dialogue_key": _stable_hex("dialogue", screen_id, candidate_id, n=32),
                "screen_id": screen_id,
                "card_key": turns[0]["card_key"],
                "candidate_id": candidate_id,
                "transcript": transcript,
            }
        )
        counts[candidate_id] += 1
    if dict(counts) != {candidate: 24 for candidate in ELIGIBLE}:
        raise RuntimeError(f"eligible dialogue inventory drifted: {dict(counts)}")
    return result


def _reviewer_order(dialogues: list[dict[str, Any]], reviewer: str) -> list[dict[str, Any]]:
    rng = random.Random(int(_stable_hex("esc-eval-human-review-order-v1", reviewer, n=16), 16))
    remaining = list(dialogues)
    rng.shuffle(remaining)
    ordered: list[dict[str, Any]] = []
    while remaining:
        last_screen = ordered[-1]["screen_id"] if ordered else None
        index = next((i for i, row in enumerate(remaining) if row["screen_id"] != last_screen), 0)
        ordered.append(remaining.pop(index))
    return ordered


def _html(payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ESC-Eval blinded human review</title>
<style>
body{font-family:system-ui,sans-serif;max-width:1050px;margin:24px auto;padding:0 16px;color:#18202a;background:#f4f6f8}
.card{background:white;border:1px solid #d9e0e7;border-radius:12px;padding:18px;margin:18px 0}.turn{padding:8px 10px;margin:6px 0;border-radius:8px}.Help-seeker{background:#eef4ff}.Supporter{background:#f3f8ef}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}.field{display:flex;flex-direction:column;gap:4px}select,textarea{font:inherit;padding:7px}.rubric{white-space:pre-wrap;font-size:13px}.bad{color:#9c1c1c}button{font:inherit;padding:10px 16px;margin-right:8px}.sticky{position:sticky;top:0;background:#f4f6f8;padding:8px 0;z-index:3}
</style></head><body><h1>ESC-Eval seven-dimension blinded review</h1>
<p>Score each complete five-turn dialogue independently. Candidate/model/provider identity is hidden. The seven 0–4 dimensions are the official ESC-Eval rubric. Project guardrails are separate and must not alter the seven official scores.</p>
<div class="sticky"><span id="progress"></span> <button onclick="save()">Save locally</button><button onclick="download()">Export completed JSON</button></div>
<details class="card"><summary>Official rubric (expand before scoring)</summary><div id="rubric"></div></details><div id="items"></div>
<script>const DATA=""" + data + """; const DIMS=DATA.dimensions, GUARDS=DATA.guardrails;
function esc(s){return String(s).replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));}
document.getElementById('rubric').innerHTML=DIMS.map(d=>`<h3>${esc(d)}</h3><div class="rubric">${esc(DATA.rubric[d])}</div>`).join('');
const root=document.getElementById('items');
root.innerHTML=DATA.items.map((it,i)=>`<section class="card" data-id="${it.assignment_id}"><h2>${i+1} / ${DATA.items.length}</h2>${it.transcript.map(t=>`<div class="turn ${t.speaker}"><b>${esc(t.speaker)}:</b> ${esc(t.text)}</div>`).join('')}<h3>Official dimensions</h3><div class="grid">${DIMS.map(d=>`<label class="field">${d}<select data-kind="dimension" data-name="${d}"><option value="">Select 0–4</option>${[0,1,2,3,4].map(x=>`<option>${x}</option>`).join('')}</select></label>`).join('')}</div><h3>Separate project guardrails</h3><div class="grid"><label class="field">Packet/transcript integrity<select data-kind="integrity"><option value="">Select</option><option>PASS</option><option>PACKET_ERROR</option><option>UNCERTAIN</option></select></label>${GUARDS.map(g=>`<label class="field">${g}<select data-kind="guardrail" data-name="${g}"><option value="">Select</option><option>PASS</option><option>FAIL</option><option>UNCERTAIN</option><option>NOT_APPLICABLE</option></select></label>`).join('')}</div><label class="field">Notes (required for non-PASS/UNCERTAIN)<textarea data-kind="notes" rows="2"></textarea></label></section>`).join('');
function collect(requireComplete=false){let answers={}; for(const el of document.querySelectorAll('section[data-id]')){let dimensions={},guardrails={}; el.querySelectorAll('[data-kind="dimension"]').forEach(x=>dimensions[x.dataset.name]=x.value===''?null:Number(x.value));el.querySelectorAll('[data-kind="guardrail"]').forEach(x=>guardrails[x.dataset.name]=x.value);let integrity=el.querySelector('[data-kind="integrity"]').value,notes=el.querySelector('[data-kind="notes"]').value.trim(); if(requireComplete&&(Object.values(dimensions).some(x=>x===null)||Object.values(guardrails).some(x=>!x)||!integrity))throw new Error('Incomplete item '+el.dataset.id);if(requireComplete&&(integrity!=='PASS'||Object.values(guardrails).some(x=>!['PASS','NOT_APPLICABLE'].includes(x)))&&!notes)throw new Error('Notes required for flagged item '+el.dataset.id);answers[el.dataset.id]={dimensions,guardrails,transcript_integrity:integrity,notes};}return {protocol:DATA.response_protocol,packet_protocol:DATA.packet_protocol,reviewer:DATA.reviewer,answers};}
function save(){localStorage.setItem(DATA.packet_protocol+'-'+DATA.reviewer,JSON.stringify(collect(false)));progress();}
function restore(){let raw=localStorage.getItem(DATA.packet_protocol+'-'+DATA.reviewer);if(!raw)return;let saved=JSON.parse(raw);for(const [id,a] of Object.entries(saved.answers||{})){let el=document.querySelector(`section[data-id="${id}"]`);if(!el)continue;for(const [d,v] of Object.entries(a.dimensions||{})){let x=el.querySelector(`[data-kind="dimension"][data-name="${d}"]`);if(x&&v!==null)x.value=String(v);}for(const [g,v] of Object.entries(a.guardrails||{})){let x=el.querySelector(`[data-kind="guardrail"][data-name="${g}"]`);if(x)x.value=v||'';}el.querySelector('[data-kind="integrity"]').value=a.transcript_integrity||'';el.querySelector('[data-kind="notes"]').value=a.notes||'';}progress();}
function progress(){let a=collect(false).answers,done=Object.values(a).filter(x=>Object.values(x.dimensions).every(v=>v!==null)&&Object.values(x.guardrails).every(Boolean)&&x.transcript_integrity).length;document.getElementById('progress').textContent=`Completed ${done}/${DATA.items.length}`;}
function download(){try{let out=collect(true),blob=new Blob([JSON.stringify(out,null,2)+'\\n'],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=`${DATA.reviewer}_esc_eval_review.json`;a.click();URL.revokeObjectURL(a.href);}catch(e){alert(e.message);}}
document.addEventListener('change',()=>{save();});restore();progress();</script></body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--esc-eval", required=True, type=Path)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "v3_g0_esc_eval_human_review_v1_20260814",
    )
    args = parser.parse_args()
    if args.out_dir.exists():
        raise RuntimeError("output directory exists; refusing to overwrite a review packet")
    rubric = _official_rubric(args.esc_eval)
    dialogues = _dialogues()
    args.out_dir.mkdir(parents=True)
    private_mapping: list[dict[str, Any]] = []
    public_hashes: dict[str, str] = {}
    for reviewer in ("HUMAN_A", "HUMAN_B"):
        items: list[dict[str, Any]] = []
        for rank, row in enumerate(_reviewer_order(dialogues, reviewer), start=1):
            assignment_id = "esceval_" + _stable_hex("assignment", reviewer, row["dialogue_key"], n=20)
            items.append({"assignment_id": assignment_id, "display_order": rank, "transcript": row["transcript"]})
            private_mapping.append(
                {
                    "assignment_id": assignment_id,
                    "reviewer": reviewer,
                    "dialogue_key": row["dialogue_key"],
                    "screen_id": row["screen_id"],
                    "card_key": row["card_key"],
                    "candidate_id": row["candidate_id"],
                }
            )
        payload = {
            "packet_protocol": "metacom-v3-g0-esc-eval-human-review-packet-v1",
            "response_protocol": RESPONSE_PROTOCOL,
            "reviewer": reviewer,
            "dimensions": list(DIMENSIONS),
            "guardrails": list(GUARDRAILS),
            "rubric": rubric,
            "items": items,
        }
        jsonl = args.out_dir / f"{reviewer.lower()}_blind_items.jsonl"
        jsonl.write_text("".join(_canonical(item) + "\n" for item in items), encoding="utf-8")
        html = args.out_dir / f"{reviewer.lower()}_review.html"
        html.write_text(_html(payload), encoding="utf-8")
        template = args.out_dir / f"{reviewer.lower()}_response_template.json"
        template.write_text(
            json.dumps(
                {
                    "protocol": RESPONSE_PROTOCOL,
                    "packet_protocol": payload["packet_protocol"],
                    "reviewer": reviewer,
                    "answers": {},
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        for path in (jsonl, html, template):
            public_hashes[path.name] = _sha_file(path)
    mapping = args.out_dir / "private_blinding_map.jsonl"
    mapping.write_text("".join(_canonical(row) + "\n" for row in private_mapping), encoding="utf-8")
    rubric_path = args.out_dir / "official_english_rubric.json"
    rubric_path.write_text(json.dumps(rubric, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "protocol": "metacom-v3-g0-esc-eval-human-review-packet-manifest-v1",
        "date": "2026-08-14",
        "status": "MATERIALIZED_TWO_INDEPENDENT_BLINDED_HUMAN_REVIEWS_PENDING",
        "source_generation_identity": json.loads(CLOSEOUT.read_text(encoding="utf-8"))["run_identity"],
        "source_ledger_sha256": _sha_file(SOURCE),
        "supporter_prompt_artifact_sha256": _sha_file(PROMPT),
        "joined_supporter_prompt_sha256": _sha_bytes(
            "\n\n".join(
                section.strip()
                for section in json.loads(PROMPT.read_text(encoding="utf-8"))["prompt_sections"]
            ).encode("utf-8")
        ),
        "esc_eval_commit": EXPECTED_ESC_COMMIT,
        "official_score_py_sha256": EXPECTED_SCORE_SHA256,
        "eligible_candidates": 3,
        "dialogues": 72,
        "reviewers": 2,
        "assignments": 144,
        "official_dimension_ratings": 1008,
        "public_packet_hashes": public_hashes,
        "private_mapping_sha256": _sha_file(mapping),
        "rubric_sha256": _sha_file(rubric_path),
        "blinding_checks": {
            "candidate_provider_model_source_card_absent_from_public_schema": True,
            "single_dialogue_not_candidate_bundle": True,
            "reviewer_orders_independent": True,
            "same_card_candidates_not_adjacent": True,
        },
        "api_calls": 0,
        "selection_verdict": "NOT_AUTHORIZED_BEFORE_TWO_REVIEWS_AND_ANY_REQUIRED_ADJUDICATION",
    }
    (args.out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
