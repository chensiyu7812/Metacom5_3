#!/usr/bin/env python3
"""Attest the pinned ES-MemEval Official RAG retrieval runtime without outcomes.

This probe exercises only the shipped BGE-M3 -> SentenceTransformer -> FAISS
session-document Top-4 path.  The texts are synthetic engineering fixtures;
the script never reads ES-MemEval targets, gold fields, Generator responses,
or scorer outputs.  Passing this probe does not freeze the Hub revision and
does not assign BGE-M3 to RS or to the Paper-1 typed-memory treatment.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

import numpy as np

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.paper1.outcome_lock import (  # noqa: E402
    assert_pre_outcome_locked,
    load_public_only_config,
)


PROTOCOL = "pm-paper1-official-rag-runtime-attestation-v1"
STATUS = "ENGINEERING_RUNTIME_ATTESTED_NOT_BASELINE_OR_RETRIEVER_FREEZE"
OFFICIAL_REPOSITORY = "slptongji/ES-MemEval"
OFFICIAL_COMMIT = "692624208acc077b8867698c1d6fcd998dee641a"
MODEL_REPO = "BAAI/bge-m3"
LOCAL_MODEL_REVISION = "9a0624b896d81da7492a910ffa53731274b6cf3d"
MODEL_FILE_SHA256 = (
    "993b2248881724788dcab8c644a91dfd63584b6e5604ff2037cb5541e1e38e7e"
)
EXPECTED_PACKAGES = {
    "faiss-cpu": "1.12.0",
    "langchain-community": "0.3.28",
    "langchain-huggingface": "0.3.1",
    "sentence-transformers": "5.1.0",
}
OFFICIAL_SOURCE_BLOBS = {
    "src/lib/shared/embedding_models/embedding_provider.py": (
        "a98510f2304afeadc415d5391db4f64a412ad6f7"
    ),
    "src/lib/shared/document_stores/vector_document_store.py": (
        "66fc315f878e40e78c2bef2315e51dfe511f3867"
    ),
    "src/lib/shared/prompt_strategies/session_wise_memory_inplace_strategy.py": (
        "e8efc593aa4fdbb9e038448500484a5de2f6a779"
    ),
    "src/lib/shared/prompt_strategies/session_wise_memory_prepend_strategy.py": (
        "a88a419a988912c899a369bba8c686f02accf586"
    ),
}

_NORMALIZE_PACKAGE = re.compile(r"[-_.]+")
_SESSION_FIXTURES = (
    "The user said a regular sleep routine helped them rest.",
    "The user described feeling overwhelmed by work stress.",
    "The user felt relief after talking with family.",
    "The user practiced slow breathing when anxiety rose.",
    "The user noticed that walking outside improved their mood.",
)
_QUERY_FIXTURE = "I feel stressed and need to calm down."


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalized_package(name: str) -> str:
    return _NORMALIZE_PACKAGE.sub("-", name).lower()


def _verify_packages() -> dict[str, str]:
    installed = {
        _normalized_package(distribution.metadata["Name"]): distribution.version
        for distribution in importlib.metadata.distributions()
        if distribution.metadata.get("Name")
    }
    mismatches = {
        name: {"expected": version, "actual": installed.get(name)}
        for name, version in EXPECTED_PACKAGES.items()
        if installed.get(name) != version
    }
    if mismatches:
        raise RuntimeError(f"Official RAG dependency drift: {mismatches}")
    return dict(sorted(EXPECTED_PACKAGES.items()))


def _verify_model_snapshot(path: Path) -> None:
    if path.name != LOCAL_MODEL_REVISION:
        raise RuntimeError(
            f"expected commit-addressed BGE-M3 revision {LOCAL_MODEL_REVISION}, got {path.name}"
        )
    model_path = path / "model.safetensors"
    if not model_path.is_file() or _sha256(model_path) != MODEL_FILE_SHA256:
        raise RuntimeError("BGE-M3 model.safetensors identity drift")


def _result_rows(rows: list[tuple[Any, float]]) -> list[dict[str, Any]]:
    return [
        {
            "rank": rank,
            "session_fixture_id": document.metadata["session_fixture_id"],
            "faiss_l2_distance": round(float(score), 8),
        }
        for rank, (document, score) in enumerate(rows, start=1)
    ]


def _run_probe(model_dir: Path, *, require_cuda: bool) -> dict[str, Any]:
    import faiss
    import torch
    from langchain_community.vectorstores import FAISS
    from langchain_core.documents import Document
    from langchain_huggingface import HuggingFaceEmbeddings

    cuda_available = torch.cuda.is_available()
    if require_cuda and not cuda_available:
        raise RuntimeError("CUDA was required but torch.cuda.is_available() is false")
    device = "cuda" if cuda_available else "cpu"
    embeddings = HuggingFaceEmbeddings(
        model_name=str(model_dir),
        model_kwargs={"device": device},
    )
    documents = [
        Document(
            page_content=text,
            metadata={"session_fixture_id": f"synthetic-session-{index}"},
        )
        for index, text in enumerate(_SESSION_FIXTURES)
    ]
    vectors = np.asarray(
        embeddings.embed_documents([document.page_content for document in documents]),
        dtype=np.float32,
    )
    if vectors.shape != (5, 1024):
        raise RuntimeError(f"unexpected BGE-M3 document matrix: {vectors.shape}")
    norms = np.linalg.norm(vectors, axis=1)
    if not np.allclose(norms, np.ones(5), atol=1e-5):
        raise RuntimeError(f"official-library BGE-M3 vectors are not normalized: {norms}")

    store = FAISS.from_documents(documents, embeddings)
    if not isinstance(store.index, faiss.IndexFlatL2):
        raise RuntimeError(f"unexpected FAISS index class: {type(store.index).__name__}")
    if store.index.ntotal != 5 or store.index.d != 1024:
        raise RuntimeError(
            f"unexpected FAISS shape: ntotal={store.index.ntotal}, d={store.index.d}"
        )
    first = _result_rows(store.similarity_search_with_score(_QUERY_FIXTURE, k=4))
    second = _result_rows(store.similarity_search_with_score(_QUERY_FIXTURE, k=4))
    if first != second:
        raise RuntimeError("repeated Official RAG Top-4 query was not deterministic")
    selected = [row["session_fixture_id"] for row in first]
    if len(first) != 4 or len(set(selected)) != 4:
        raise RuntimeError(f"Official RAG probe did not return four unique sessions: {selected}")

    return {
        "device": device,
        "cuda_available": cuda_available,
        "gpu_name": torch.cuda.get_device_name(0) if cuda_available else None,
        "torch_version": torch.__version__,
        "torch_cuda_version": torch.version.cuda,
        "embedding_client_class": type(embeddings._client).__name__,
        "document_embedding_shape": [5, 1024],
        "document_vector_l2_norms": [round(float(value), 8) for value in norms],
        "faiss_index_class": type(store.index).__name__,
        "faiss_metric": "L2_DISTANCE_LOWER_IS_CLOSER",
        "faiss_dimension": store.index.d,
        "faiss_document_count": store.index.ntotal,
        "top_k": 4,
        "repeat_exact": True,
        "top4": first,
    }


def build_attestation(args: argparse.Namespace) -> dict[str, Any]:
    config = load_public_only_config(args.config)
    assert_pre_outcome_locked(config)
    if os.environ.get("HF_HUB_OFFLINE") != "1" or os.environ.get(
        "TRANSFORMERS_OFFLINE"
    ) != "1":
        raise RuntimeError("Official RAG attestation requires both offline-mode variables")
    _verify_model_snapshot(args.bge_m3_dir)
    package_versions = _verify_packages()
    probe = _run_probe(args.bge_m3_dir, require_cuda=args.require_cuda)
    fixture_hashes = [
        _sha256_bytes(text.encode("utf-8")) for text in _SESSION_FIXTURES
    ]
    return {
        "protocol": PROTOCOL,
        "status": STATUS,
        "outcome_calls": 0,
        "formal_unlock": False,
        "attestation_inputs": {
            "script_sha256": _sha256(Path(__file__).resolve()),
            "public_only_config_sha256": _sha256(args.config),
            "environment_lock_sha256": _sha256(
                PROJECT / "environments/requirements-paper1-py311.lock.txt"
            ),
            "local_environment_attestation_sha256": _sha256(
                PROJECT
                / "data/paper1_authority/paper1_local_environment_attestation_v1.json"
            ),
        },
        "scope": {
            "arm": "ES_MEMEVAL_OFFICIAL_RAG_BASELINE_ENGINEERING_PATH",
            "typed_memory_method_changed": False,
            "rs_retriever_selected": False,
            "benchmark_targets_read": False,
            "benchmark_gold_or_scorer_outputs_read": False,
            "generator_calls": 0,
            "winner_selected": False,
        },
        "official_source_binding": {
            "repository": OFFICIAL_REPOSITORY,
            "commit": OFFICIAL_COMMIT,
            "source_blobs": OFFICIAL_SOURCE_BLOBS,
            "model_id": MODEL_REPO,
            "model_revision_in_official_source": None,
            "embedding_api": "langchain_huggingface.HuggingFaceEmbeddings",
            "vector_store": "langchain_community.vectorstores.FAISS",
            "document_grain": "one_historical_session_per_Document",
            "retrieval_k": 4,
        },
        "local_model_binding": {
            "repo": MODEL_REPO,
            "revision": LOCAL_MODEL_REVISION,
            "model_safetensors_sha256": MODEL_FILE_SHA256,
            "revision_status": "COMMIT_ADDRESSED_HUB_PR130_SNAPSHOT_NOT_RESEARCH_FREEZE",
            "official_unpinned_main_weight_equivalence": "NOT_ESTABLISHED",
        },
        "runtime": {
            "offline": True,
            "package_versions": package_versions,
            "fixture_document_count": len(_SESSION_FIXTURES),
            "fixture_document_sha256": fixture_hashes,
            "query_sha256": _sha256_bytes(_QUERY_FIXTURE.encode("utf-8")),
            "probe": probe,
        },
        "interpretation": {
            "established": [
                "exact official retrieval-core package versions import together",
                "commit-addressed local BGE-M3 loads through HuggingFaceEmbeddings",
                "SentenceTransformer emits normalized 1024-dimensional dense vectors",
                "FAISS indexes session-level Documents and returns deterministic Top-4",
            ],
            "not_established": [
                "official benchmark performance",
                "equivalence to an unpinned upstream BGE-M3 main weight snapshot",
                "final local model revision freeze",
                "Typed Memory retrieval design or utility",
                "RS retriever selection or utility",
            ],
        },
        "pending_m2_freeze": [
            "select_and_bind_the_local_BGE_M3_revision_for_official_RAG_with_unpinned_upstream_disclosure",
            "bind_task_specific_official_RAG_prompt_and_truncation_wrappers",
            "bind_official_RAG_runner_and_cost_logging_without_changing_Typed_Memory",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT / "configs/paper1_public_only.yaml",
    )
    parser.add_argument("--bge-m3-dir", type=Path, required=True)
    parser.add_argument("--require-cuda", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            PROJECT
            / "data/paper1_authority/paper1_official_rag_runtime_attestation_v1.json"
        ),
    )
    args = parser.parse_args()
    payload = build_attestation(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
