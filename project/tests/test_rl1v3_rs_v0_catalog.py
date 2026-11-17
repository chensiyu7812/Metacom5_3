"""Provenance/category safety and actual B writer input compatibility, CPU only."""
import copy
import json
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator
from metacom_pm.rl1v3.bank import rs_v0_catalog as C
from metacom_pm.rl1v3.bank.v0_port import load_bank
from metacom_pm.rl1v3.io import canonical_json, object_sha256
from metacom_pm.rl1v3.needs.sources import PrefixContext
from metacom_pm.rl1v3.needs.protocol import build_pack, render_messages

ROOT=Path(__file__).resolve().parents[2]

@pytest.fixture(scope="module")
def assets():
    bank,_=load_bank(ROOT)
    return bank,C.build(ROOT,bank)


def test_original_annotation_counts_and_nonadditive_layers(assets):
    bank,c=assets
    assert c.data["counts"]==dict(cases=875,annotated_supporter_turns=12403,
        label_counts=dict(question=2568,affirmation_and_reassurance=1953,self_disclosure=1149,
                          providing_suggestions=1991,others=2252,restatement_or_paraphrasing=706,
                          reflection_of_feelings=976,information=808),
        selectable_categories=7,unknown=0,linked_legacy_strategy_ids=11590,linked_legacy_treatment_ids=13172)
    assert len(c.entries)==8 and "others" not in c.selectable
    assert {r["record_id"] for r in c.data["cases"]}=={r.record_id for r in bank.records if r.head=="RS"}
    assert all(e["definition"]=="unknown" and e["quality"]=="unverified" for e in c.entries)
    assert c.data["is_a4_method_catalog"] is False


@pytest.mark.parametrize("label",[None,"New strategy","question",""])
def test_unknown_is_not_inferred(label):
    assert C.classify(label)=="unknown"


def test_family_and_source_span_validation(assets):
    bank,c=assets
    from metacom_pm.rl1v3.io import decode_contract
    from metacom_pm.rl1v3.contracts import SourceSpan
    for row in c.data["evidence"]:
        source=bank.registry.by_id[row["source_id"]].source
        assert source.source_split=="train"
        assert row["source_family"]==source.family_id
        assert row["source_family"] not in bank.registry.excluded_families
        ref=decode_contract(SourceSpan,canonical_json(row["source_span"]))
        ref.verify(source)
        assert ref.speaker=="supporter"
    assert len({r["evidence_id"] for r in c.data["evidence"]})==12403


def test_catalog_schema_and_strict_quality(assets):
    _,c=assets
    schema=json.loads((ROOT/'project/schemas/rl1v3_rs_v0/StrategyCatalog.schema.json').read_text())
    validator=Draft202012Validator(schema)
    validator.validate(c.data)
    invalid=copy.deepcopy(c.data);invalid["quality"]="verified"
    assert list(validator.iter_errors(invalid))
    invalid=copy.deepcopy(c.data);invalid["entries"][0]["professional_advice"]="do this"
    assert list(validator.iter_errors(invalid))


@pytest.mark.parametrize("resign",[False,True])
def test_tampered_provenance_rejected_even_when_resigned(assets,tmp_path,resign):
    bank,c=assets
    bad=copy.deepcopy(c.data);bad["evidence"][0]["source_span"]["exact_quote"]="fabrication"
    if resign:
        bad["catalog_id"]=C.PROTOCOL+":"+object_sha256({k:v for k,v in bad.items() if k!="catalog_id"})
    path=tmp_path/'bad.json';path.write_text(canonical_json(bad))
    with pytest.raises(ValueError,match="identity|annotations"):
        C.load(path,root=ROOT,bank=bank)


def test_roundtrip_and_no_promoted_guidance(assets,tmp_path):
    bank,c=assets;path=tmp_path/'catalog.json'
    C.save(c,path)
    assert C.load(path,root=ROOT,bank=bank).sha256==c.sha256
    public=canonical_json(c.as_dict())
    assert all(word not in public for word in ("guidance_text","treatment_ids","source_span","exact_quote"))
    assert "unverified" in public and "engineering_needcard_input_only" in public


def test_24_actual_b_needcard_input_packs_without_model(assets):
    bank,c=assets
    rows=[json.loads(x) for x in (ROOT/'project/outputs/pm_rl1/v3/B1/coverage_sample_v1.jsonl').read_text().splitlines()]
    assert len(rows)==24
    for row in rows:
        p=bank.registry.prefix(row["owner_id"],row["session_id"],row["cut_turn"])
        assert p.prefix_id==row["prefix_id"]
        current,history=bank.registry.context(p)
        ctx=PrefixContext(prefix=p,current=current,history=history,row=row)
        pack=build_pack(ctx,c.for_needcard_writer())
        assert pack["status"]=="ready"
        messages=render_messages(pack)
        data=json.loads(messages[-1]["content"].split('\n',1)[1])
        assert len(data["METHOD_CATALOG"])==7
        assert all("unverified" in x["description"] and "definition unknown" in x["description"] for x in data["METHOD_CATALOG"])
        assert all(s.chronological_rank<p.cutoff_rank and s.owner_id==p.owner_id for s in history)
