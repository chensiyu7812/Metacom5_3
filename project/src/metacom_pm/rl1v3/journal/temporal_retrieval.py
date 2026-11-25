"""Frozen CPU retrieval comparison; reference atoms are read only after ranking.

Original RET-v1 keeps its official end-history scope. New date-constrained
methods are separate identities, never edits to the old bank or admissions.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time

from .evidence_audit import parse_question_time
from .behavior_compare import EXPECTED_REVISION, EXPECTED_WEIGHTS_SHA256

PROTOCOL = "pmrl1-j-temporal-retrieval-comparison-v1"
METHODS = ("RET-v1-end-history", "strict-lexical-v1", "strict-bge-v1", "strict-hybrid-rrf-v1")
ENTITY_EXCLUSIONS = frozenset("What Who Where When Why How Which Is Are Has Have Does Did Do As Of On By The A An I He She They It His Her Their Seeker User January Jenuary February March April May June July August September October November December".split())
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "
RAW_BANNER = "SOURCE_EXACT completed historical session. Statements retain their original speaker; present validity and real-world truth are unknown.\n"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line]


def write(path, value, lines=False):
    with Path(path).open("x") as f:
        if lines:
            for row in value:
                f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        else:
            json.dump(value, f, ensure_ascii=False, sort_keys=True, indent=2)
            f.write("\n")


def words(text):
    return frozenset(re.findall(r"[a-z0-9']+", text.casefold()))


def entities(question):
    """Transparent proper-token proxy, not an entity-resolution model."""
    return frozenset(w.lower() for w in re.findall(r"\b[A-Z][a-z]+(?:'[a-z]+)?\b", question)
                     if w not in ENTITY_EXCLUSIONS)


def temporal_focus(question, scope):
    return scope["upper"] is not None or bool(re.search(r"\b(current|currently|still|latest|recent|recently|finally|now)\b", question, re.I))


def eligible(records, owner, cutoff=None):
    owned = [r for r in records if r["owner_id"] == owner]
    if any(not r["reported_at"]["date"] for r in owned):
        raise ValueError("missing report date cannot silently enter temporal comparison")
    allowed = [r for r in owned if cutoff is None or r["reported_at"]["date"] <= cutoff]
    frontier = len(allowed)
    if sorted(r["source_rank"] for r in allowed) != list(range(frontier)):
        raise ValueError("report-date frontier is not a completed chronological prefix")
    if any(r["ready_at"]["session_rank"] > frontier for r in allowed):
        raise ValueError("source not ready at selected prefix")
    return allowed


def order_scores(records, scores):
    return sorted(records, key=lambda r: (-scores[r["record_id"]], -r["source_rank"], r["record_id"]))


def lexical(records, question):
    query = words(question)
    scores = {r["record_id"]: len(query & words(r["reading_text"])) / max(1, len(query)) for r in records}
    return order_scores(records, scores), scores


def hybrid(records, question, scope, lexical_scores, semantic_scores):
    channels = [lexical_scores, semantic_scores]
    names = entities(question)
    if names:
        channels.append({r["record_id"]: len(names & words(r["reading_text"])) / len(names) for r in records})
    if temporal_focus(question, scope):
        channels.append({r["record_id"]: r["source_rank"] for r in records})
    # Ties within a component share competition rank, avoiding arbitrary
    # record-ID/entity ties being promoted as evidence of entity relevance.
    ranks = []
    for channel in channels:
        levels = sorted(set(channel.values()), reverse=True)
        rank_of = {value: 1 + sum(v > value for v in channel.values()) for value in levels}
        ranks.append({rid: rank_of[value] for rid, value in channel.items()})
    scores = {r["record_id"]: sum(1 / (60 + rank[r["record_id"]]) for rank in ranks) for r in records}
    return order_scores(records, scores), scores, len(channels)


def chunks(ids, size=480, overlap=64):
    if not ids:
        return [[]]
    output = []
    start = 0
    while start < len(ids):
        output.append(ids[start:start + size])
        if start + size >= len(ids):
            break
        start += size - overlap
    return output


class Encoder:
    def __init__(self, path, records):
        import numpy as np
        import torch
        from transformers import AutoModel, AutoTokenizer
        self.np, self.torch = np, torch
        torch.set_num_threads(4)
        torch.set_num_interop_threads(1)
        self.tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True, trust_remote_code=False)
        self.model = AutoModel.from_pretrained(path, local_files_only=True, trust_remote_code=False, attn_implementation="eager").to("cpu").eval()
        self.query_cache = {}
        self.positions = {}
        all_chunks = []
        for r in records:
            pieces = chunks(self.tokenizer.encode(r["reading_text"], add_special_tokens=False))
            start = len(all_chunks)
            all_chunks.extend(pieces)
            self.positions[r["record_id"]] = (start, len(all_chunks))
        self.document_chunks = len(all_chunks)
        self.vectors = self.encode_ids(all_chunks)

    def encode_ids(self, inputs):
        out = []
        with self.torch.inference_mode():
            for start in range(0, len(inputs), 16):
                encoded = [self.tokenizer.prepare_for_model(ids, add_special_tokens=True, truncation=False) for ids in inputs[start:start + 16]]
                batch = self.tokenizer.pad(encoded, padding=True, return_tensors="pt")
                embedding = self.model(**batch).last_hidden_state[:, 0]
                out.append(self.torch.nn.functional.normalize(embedding, p=2, dim=1).cpu().numpy())
        return self.np.concatenate(out, axis=0)

    def score(self, records, question, *, cached):
        if not cached or question not in self.query_cache:
            ids = self.tokenizer.encode(QUERY_INSTRUCTION + question, add_special_tokens=False)
            if len(ids) > 510:
                raise ValueError("query exceeds model length; no silent truncation")
            self.query_cache[question] = self.encode_ids([ids])[0]
        query = self.query_cache[question]
        scores = {}
        for record in records:
            lo, hi = self.positions[record["record_id"]]
            scores[record["record_id"]] = float((self.vectors[lo:hi] @ query).max())
        return scores


def rank(records, owner, question, method, scope, bound, encoder, cached):
    cutoff = None if method == METHODS[0] else scope[bound]
    candidates = eligible(records, owner, cutoff)
    lex_rank, lex_scores = lexical(candidates, question)
    components = 1
    if method in METHODS[:2]:
        ordered, scores = lex_rank, lex_scores
    else:
        semantic = encoder.score(candidates, question, cached=cached)
        if method == METHODS[2]:
            ordered, scores = order_scores(candidates, semantic), semantic
        else:
            ordered, scores, components = hybrid(candidates, question, scope, lex_scores, semantic)
    return candidates, ordered[:4], scores, components


def validate_sources(records, ledger):
    lookup = {(r["owner_id"], r["session_id"]): r for r in ledger}
    for r in records:
        row = lookup[(r["owner_id"], r["parent_session_id"])]
        if RAW_BANNER + row["text"] != r["reading_text"] or row["reported_at"] != r["reported_at"] or row["ready_at"] != r["ready_at"]:
            raise ValueError("existing source Ledger binding differs")
    for owner in {r["owner_id"] for r in records}:
        ordered = sorted((r for r in records if r["owner_id"] == owner), key=lambda r: r["source_rank"])
        dates = [r["reported_at"]["date"] for r in ordered]
        if dates != sorted(dates):
            raise ValueError("source ranks and report dates disagree")
        eligible(records, owner)


def run(memory, model, native_model, assets, output):
    """No audit/gold path accepted by this retrieval-only stage."""
    started = time.perf_counter()
    memory, model, output = map(Path, (memory, model, output))
    output.mkdir(parents=True, exist_ok=False)
    os.environ.update(CUDA_VISIBLE_DEVICES="", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", TOKENIZERS_PARALLELISM="false")
    if model.name != EXPECTED_REVISION or sha(model / "model.safetensors") != EXPECTED_WEIGHTS_SHA256:
        raise ValueError("local BGE identity differs")
    tasks = read_rows(memory / "tasks_runtime.jsonl")
    records = read_rows(memory / "resources_private.jsonl")
    original = {r["task_id"]: r for r in read_rows(memory / "request_material_private.jsonl") if r["arm"] == "RET"}
    byid = {r["record_id"]: r for r in records}
    ledger = [json.loads(p.read_text()) for p in sorted((memory / "ledger").glob("*.json"))]
    validate_sources(records, ledger)
    # Owner identity is copied from the frozen original retrieval's record IDs;
    # neither original DP/evidence sessions nor the evaluation file are read.
    owners = {}
    for task in tasks:
        identities = {byid[rid]["owner_id"] for rid in original[task["task_id"]]["private_source_record_ids"]}
        if len(identities) != 1:
            raise ValueError("ambiguous original task owner binding")
        owners[task["task_id"]] = identities.pop()
    config = dict(protocol=PROTOCOL, methods=METHODS, tasks=len(tasks), sessions=len(records), top_k=4,
        device="cpu", cpu_threads=4, encoder_revision=EXPECTED_REVISION, encoder_weights_sha256=EXPECTED_WEIGHTS_SHA256,
        bge=dict(pooling="normalized CLS; session=max chunk cosine", chunk_wordpieces=480, overlap=64, query_instruction=QUERY_INSTRUCTION, batch_size=16),
        hybrid=dict(fusion="equal reciprocal rank, k=60, tied component values share rank", channels="lexical + semantic; query proper-token match if nonempty; source recency if explicit date/currentness marker", rationale="Complement word overlap with frozen semantics, name disambiguation and source recency. These are fixed proxies, not evidence of effect or event-state validity."),
        temporal=dict(original="official end-history; no retrospective leakage relabel", strict="owner/report-date/ready-rank filter before scoring", month_interval="lower bound primary; upper bound separately frozen sensitivity", missing_explicit_date="end-history retained", same_day="completed same-day sessions admitted at end-of-day only; no clock precision"),
        latency="model/index preparation separate; cold_query means no query cache, resident index; hot_query reuses query embedding. One fixed pass each, not OS-cache-cold or end-to-end client latency.",
        evidence_isolation="Only questions, raw reports and owner/source metadata enter ranking. Frozen atom audit is opened by separate evaluate stage after ranking manifest exists.",
        no_hyperparameter_search=True, selection_after_outcomes=False,
        source_inputs={name:sha(memory/name) for name in ("tasks_runtime.jsonl","resources_private.jsonl","request_material_private.jsonl")},
        ledger_sha256=digest({p.name:sha(p) for p in sorted((memory/"ledger").glob("*.json"))}), code_sha256=sha(__file__))
    write(output / "PRECOMMITTED_CONFIG.json", config)
    index_start = time.perf_counter()
    encoder = Encoder(model, records)
    index_seconds = time.perf_counter() - index_start
    from ..retrieve.native_tokens import NativeTokenizer
    tokenizer = NativeTokenizer(native_model, assets)
    results = []
    for task in tasks:
        question = task["visible_prefix"]["turns"][0]["text"]
        scope = parse_question_time(question)
        owner = owners[task["task_id"]]
        for method in METHODS:
            bounds = ["lower", "upper"] if method != METHODS[0] and scope["kind"] == "explicit_month_interval" else ["lower"]
            for bound in bounds:
                before = time.perf_counter()
                candidates, selected, scores, components = rank(records, owner, question, method, scope, bound, encoder, False)
                cold = time.perf_counter() - before
                before = time.perf_counter()
                _, repeat, _, _ = rank(records, owner, question, method, scope, bound, encoder, True)
                hot = time.perf_counter() - before
                if [r["record_id"] for r in selected] != [r["record_id"] for r in repeat]:
                    raise ValueError("cold/hot rankings differ")
                ordered = sorted(selected, key=lambda r: (r["source_rank"], r["record_id"]))
                if method == METHODS[0] and [r["record_id"] for r in ordered] != original[task["task_id"]]["private_source_record_ids"]:
                    raise ValueError("original RET-v1 reproduction differs")
                text = "\n\n".join(f'Completed historical session; reported {r["reported_at"]["date"]}:\n'+r["reading_text"] for r in ordered)
                identity = dict(protocol=PROTOCOL, scope="end-history" if method==METHODS[0] or scope["lower"] is None else "strict-reported-date", bound=bound, cutoff=None if method==METHODS[0] else scope[bound], owner=owner,
                    frontier=[(r["record_id"],r["original_raw_identity"]) for r in candidates], query_sha256=digest(question), method=method)
                results.append(dict(task_id=task["task_id"], owner_id=owner, question=question, scope=scope, method=method, bound=bound,
                    retrieval_identity=digest(identity), cutoff_identity=identity, candidate_count=len(candidates), components=components,
                    selected_session_ids=[r["parent_session_id"] for r in ordered], selected_record_ids=[r["record_id"] for r in ordered],
                    ranked_session_ids=[r["parent_session_id"] for r in selected], selected_scores=[scores[r["record_id"]] for r in selected],
                    reading_text=text, reading_tokens=tokenizer.count(text), cold_query_seconds=cold, hot_query_seconds=hot,
                    selected_reports=[dict(session_id=r["parent_session_id"],date=r["reported_at"]["date"],rank=r["source_rank"],ready_rank=r["ready_at"]["session_rank"]) for r in ordered],
                    future_reports_vs_explicit_upper=sum(scope["upper"] is not None and r["reported_at"]["date"]>scope["upper"] for r in ordered)))
    write(output / "RANKINGS_PRIVATE.jsonl", results, lines=True)
    timing = dict(index_model_prepare_seconds=index_seconds, document_chunks=encoder.document_chunks,
                  total_retrieval_stage_seconds=time.perf_counter()-started, tokenizer_identity=tokenizer.identity,
                  thread_count=4, device="cpu", generator_calls=0)
    write(output / "TIMING.json", timing)
    write(output / "RANKING_FREEZE.json", dict(protocol=PROTOCOL, frozen_at_utc=datetime.now(timezone.utc).isoformat(),
        config_sha256=sha(output/"PRECOMMITTED_CONFIG.json"), rankings_sha256=sha(output/"RANKINGS_PRIVATE.jsonl"),
        code_sha256=sha(__file__), audit_accessed_by_retrieval=False, rows=len(results), original_RET_reproduced=30))
    return timing


def evidence_coverage(atoms, sessions, validity):
    supported = [a for a in atoms if a.get("required",True) and a[validity] in {"supported","calendar_derived"}]
    details = []
    for a in supported:
        covered = bool(a["sufficient_source_groups"]) and any(all(ref.rsplit(":",1)[0] in sessions for ref in g) for g in a["sufficient_source_groups"])
        details.append(dict(atom_id=a["atom_id"], sufficient_group_covered=covered))
    unknown = [a for a in atoms if a.get("required",True) and a[validity] not in {"supported","calendar_derived","absence_supported"}]
    absence = [a for a in atoms if a.get("required",True) and a[validity]=="absence_supported"]
    status = "reference_pending_or_scope_conflict" if unknown else "archive_absence_review" if absence else "documented_groups_covered" if all(x["sufficient_group_covered"] for x in details) else "evidence_insufficient"
    return dict(status=status,supported_necessary_atoms=len(details),covered_sufficient_groups=sum(x["sufficient_group_covered"] for x in details),
                unknown_necessary_atoms=len(unknown),absence_necessary_atoms=len(absence), atoms=details)


def evaluate(output, audit_path):
    """Post-freeze read-only evaluator; never modifies source/ranks or picks method."""
    output = Path(output)
    frozen = json.loads((output/"RANKING_FREEZE.json").read_text())
    if sha(output/"RANKINGS_PRIVATE.jsonl") != frozen["rankings_sha256"] or sha(__file__) != frozen["code_sha256"]:
        raise ValueError("ranking/code changed before evaluation")
    audit = {r["task_id"]:r for r in read_rows(audit_path)}
    rows = read_rows(output/"RANKINGS_PRIVATE.jsonl")
    evaluations = []
    for row in rows:
        task = audit[row["task_id"]]
        if task["question"] != row["question"]:
            raise ValueError("audit question differs")
        supplied = set(row["selected_session_ids"])
        strict = {r["session_id"] for r in row["selected_reports"] if row["scope"]["upper"] is None or r["date"]<=row["scope"]["lower"]}
        main = evidence_coverage(task["atoms"],supplied,"status_end_history" if row["method"]==METHODS[0] else "status_explicit_date")
        sensitivity = evidence_coverage(task["atoms"],strict,"status_explicit_date")
        conflict_refs = {e["session_id"] for a in task["atoms"] for e in a["source_evidence"] if e["relation"]=="conflict"}
        evaluations.append(dict(task_id=row["task_id"],method=row["method"],bound=row["bound"],capability=task["capability"],
            question=row["question"],gold=task["gold"],selected_session_ids=row["selected_session_ids"],scope=row["scope"],
            main=main,strict_lower_sensitivity=sensitivity,selected_conflict_source_count=len(conflict_refs&supplied),
            reference_statuses=dict(Counter(a["status_explicit_date"] for a in task["atoms"] if a.get("required",True))),
            future_reports_vs_explicit_upper=row["future_reports_vs_explicit_upper"],reading_tokens=row["reading_tokens"],
            cold_query_seconds=row["cold_query_seconds"],hot_query_seconds=row["hot_query_seconds"]))
    import statistics
    aggregate = {}
    for method in METHODS:
        chosen=[r for r in evaluations if r["method"]==method and r["bound"]=="lower"]
        aggregate[method]=dict(tasks=len(chosen),coverage_status=dict(Counter(r["main"]["status"] for r in chosen)),
            supported_necessary_atoms=sum(r["main"]["supported_necessary_atoms"] for r in chosen),
            covered_sufficient_groups=sum(r["main"]["covered_sufficient_groups"] for r in chosen),
            unknown_necessary_atoms=sum(r["main"]["unknown_necessary_atoms"] for r in chosen),
            strict_sensitivity_status=dict(Counter(r["strict_lower_sensitivity"]["status"] for r in chosen)),
            tasks_with_future_reports=sum(r["future_reports_vs_explicit_upper"]>0 for r in chosen),
            future_report_count=sum(r["future_reports_vs_explicit_upper"] for r in chosen),
            selected_conflict_source_count=sum(r["selected_conflict_source_count"] for r in chosen),
            reading_tokens=dict(total=sum(r["reading_tokens"] for r in chosen),median=statistics.median(r["reading_tokens"] for r in chosen),max=max(r["reading_tokens"] for r in chosen)),
            cold_query_ms=dict(median=1000*statistics.median(r["cold_query_seconds"] for r in chosen),max=1000*max(r["cold_query_seconds"] for r in chosen)),
            hot_query_ms=dict(median=1000*statistics.median(r["hot_query_seconds"] for r in chosen),max=1000*max(r["hot_query_seconds"] for r in chosen)))
    public=dict(protocol=PROTOCOL,by_method=aggregate,tasks=30,source_sessions=91,source_time_order_verified=True,
        original_RET_v1_full_history_reproduced=30,months_keep_interval=True,month_upper_sensitivity_rows=sum(r["bound"]=="upper" for r in evaluations),
        date_scope_counts=dict(Counter(r["scope"]["kind"] for r in rows if r["method"]==METHODS[0])),
        frozen_rankings_sha256=frozen["rankings_sha256"],evaluation_audit_sha256=sha(audit_path),
        timing=json.loads((output/"TIMING.json").read_text()),
        qualification="Reference sidecar is same-model assistant source review, not independent human qualification; coverage is source-group delivery, not answer quality or reward.",
        limits=["RET-v1 retains official end-history scope; later reports are only a strict-date sensitivity, not retrospectively reclassified as leakage.",
                "Four owners in three prior development family groups; no held-out effectiveness estimate.",
                "Month-only cutoffs remain an interval; lower-bound primary and upper-bound sensitivity are both retained.",
                "BGE max chunk similarity favors some longer sessions; no tuning or alternative pooling search was performed.",
                "Recency is report order, not event resolution; entity matching is a capitalization proxy.",
                "Cold-query timing uses a resident index with an uncached query; model/index startup is separate, not end-to-end latency.",
                "No method selected after observing coverage; no generation, training labels or formal rewards."])
    write(output/"EVALUATION_PRIVATE.jsonl",evaluations,lines=True)
    write(output/"PUBLIC_AGGREGATE.json",public)
    table=["# 全部30题时间合法检索比较（私有）", "", "检索先冻结；原问题、gold、人工原子仅在本表评价阶段合流。覆盖是必要原子充分来源组供应，非回答正确率。RET-v1仍为完整历史身份；未来来源仅为另一严格日期口径下的敏感性。", "", "|Task ID|Question|Method|Date bound|Selected sessions|Coverage|Groups|Future reports|Reading tokens|", "|---|---|---|---|---|---|---:|---:|---:|"]
    for r in evaluations:
        table.append("|"+"|".join(str(v).replace("|","/") for v in (r["task_id"],r["question"],r["method"],r["bound"],",".join(r["selected_session_ids"]),r["main"]["status"],f'{r["main"]["covered_sufficient_groups"]}/{r["main"]["supported_necessary_atoms"]}',r["future_reports_vs_explicit_upper"],r["reading_tokens"]))+"|")
    with (output/"QA30_COMPARISON_PRIVATE.md").open("x") as f:f.write("\n".join(table)+"\n")
    write(output/"EVALUATION_MANIFEST.json",dict(audit_read_after_ranking_freeze=True,ranking_freeze_sha256=sha(output/"RANKING_FREEZE.json"),audit_sha256=sha(audit_path),public_sha256=sha(output/"PUBLIC_AGGREGATE.json"),evaluation_sha256=sha(output/"EVALUATION_PRIVATE.jsonl"),generator_calls=0,reward=None))
    return public
