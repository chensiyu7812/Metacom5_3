#!/usr/bin/env python3
"""Fail-closed zero-outcome attestation for the Paper-1 local runtime.

This verifies engineering capability only. It does not freeze the retriever,
token cap, renderer, feature schema, or NVIDIA NIM tokenizer parity, and it
never reads benchmark outcomes.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import site
import sys
from typing import Any


PROTOCOL = "pm-paper1-local-environment-attestation-v1"
STATUS = "ENGINEERING_CAPABLE_NOT_RESEARCH_FROZEN"
LLAMA_REPO = "NousResearch/Meta-Llama-3.1-8B-Instruct"
LLAMA_REVISION = "d10aef7999a2b5ba950ab3974312feeedbfe0b77"
BGE_REPO = "BAAI/bge-small-en-v1.5"
BGE_REVISION = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
BGE_M3_REPO = "BAAI/bge-m3"
BGE_M3_REVISION = "9a0624b896d81da7492a910ffa53731274b6cf3d"

LLAMA_FILES = {
    "tokenizer.json": "79e3e522635f3171300913bb421464a87de6222182a0570b9b2ccba2a964b2b4",
    "tokenizer_config.json": "24e8a6dc2547164b7002e3125f10b415105644fcf02bf9ad8b674c87b1eaaed6",
    "special_tokens_map.json": "6f38c73729248f6c127296386e3cdde96e254636cc58b4169d3fd32328d9a8ec",
}
BGE_FILES = {
    "model.safetensors": "3c9f31665447c8911517620762200d2245a2518d6e7208acc78cd9db317e21ad",
    "config.json": "094f8e891b932f2000c92cfc663bac4c62069f5d8af5b5278c4306aef3084750",
    "tokenizer.json": "d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66",
    "tokenizer_config.json": "9261e7d79b44c8195c1cada2b453e55b00aeb81e907a6664974b4d7776172ab3",
    "vocab.txt": "07eced375cec144d27c900241f3e339478dec958f92fddbc551f295c992038a3",
}
BGE_M3_FILES = {
    "1_Pooling/config.json": "e54c164a07274f2eb45bb724f54a79d1efcc90c41573887cd9a29aeee0597352",
    "config.json": "26159e7ad065073448460117eb24b7a4572f6f4e78eadff65dc0a11c052449fa",
    "config_sentence_transformers.json": "1eef72430e7194a1e59680e635aed81ffa083f05668dbc5bb1c56c04c0999c38",
    "modules.json": "84e40c8e006c9b1d6c122e02cba9b02458120b5fb0c87b746c41e0207cf642cf",
    "model.safetensors": "993b2248881724788dcab8c644a91dfd63584b6e5604ff2037cb5541e1e38e7e",
    "sentence_bert_config.json": "eb9b44b13c0f52a3b3685c3b1cbdea1ba8b04bea123b98f61610048940776eb1",
    "sentencepiece.bpe.model": "cfc8146abe2a0488e9e2a0c56de7952f7c11ab059eca145a0a727afce0db2865",
    "special_tokens_map.json": "8c785abebea9ae3257b61681b4e6fd8365ceafde980c21970d001e834cf10835",
    "tokenizer.json": "21106b6d7dab2952c1d496fb21d5dc9db75c28ed361a05f5020bbba27810dd08",
    "tokenizer_config.json": "a62b2b6784f990259fddef5f16388693a8043be4f69179e6a5257eeb3f9abac4",
}

_NORMALIZE_PACKAGE = re.compile(r"[-_.]+")


def _normalized_package(name: str) -> str:
    return _NORMALIZE_PACKAGE.sub("-", name).lower()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_lock(path: Path) -> dict[str, str]:
    packages: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "==" not in line:
            raise ValueError(f"unrecognized lock entry: {line!r}")
        name, version = line.split("==", 1)
        normalized = _normalized_package(name)
        if normalized in packages:
            raise ValueError(f"duplicate normalized lock entry: {normalized}")
        packages[normalized] = version
    if not packages:
        raise ValueError("lock file is empty")
    return packages


def verify_files(root: Path, expected: dict[str, str]) -> dict[str, str]:
    if not root.is_dir():
        raise FileNotFoundError(f"snapshot directory is missing: {root}")
    actual: dict[str, str] = {}
    for relative, expected_sha in expected.items():
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(f"required snapshot file is missing: {relative}")
        actual_sha = _sha256(path)
        if actual_sha != expected_sha:
            raise ValueError(
                f"snapshot hash mismatch for {relative}: {actual_sha} != {expected_sha}"
            )
        actual[relative] = actual_sha
    return actual


def _distribution_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name")
        if not name:
            continue
        normalized = _normalized_package(name)
        version = distribution.version
        previous = versions.get(normalized)
        if previous is not None and previous != version:
            raise ValueError(
                f"multiple installed versions for {normalized}: {previous}, {version}"
            )
        versions[normalized] = version
    return versions


def verify_locked_environment(lock_path: Path) -> dict[str, str]:
    expected = parse_lock(lock_path)
    actual = _distribution_versions()
    missing = sorted(set(expected) - set(actual))
    mismatched = {
        name: {"expected": expected[name], "actual": actual[name]}
        for name in sorted(set(expected) & set(actual))
        if expected[name] != actual[name]
    }
    allowed_extra = {"metacom-pm"}
    unexpected = sorted(set(actual) - set(expected) - allowed_extra)
    if missing or mismatched or unexpected:
        raise ValueError(
            json.dumps(
                {
                    "missing": missing,
                    "mismatched": mismatched,
                    "unexpected": unexpected,
                },
                sort_keys=True,
            )
        )
    if actual.get("metacom-pm") != "4.0.0":
        raise ValueError("editable metacom-pm==4.0.0 is not installed")
    return {name: expected[name] for name in sorted(expected)}


def verify_import_boundary() -> dict[str, str]:
    if os.environ.get("PYTHONNOUSERSITE") != "1" or site.ENABLE_USER_SITE:
        raise RuntimeError("Paper-1 runtime requires PYTHONNOUSERSITE=1")
    prefix = Path(sys.prefix).resolve()
    imports: dict[str, str] = {}
    for module_name in (
        "huggingface_hub",
        "numpy",
        "pydantic",
        "pytest",
        "sklearn",
        "tokenizers",
        "torch",
        "transformers",
    ):
        module = importlib.import_module(module_name)
        module_path = Path(module.__file__).resolve()
        if not module_path.is_relative_to(prefix):
            raise RuntimeError(
                f"{module_name} imported outside the active environment: {module_path}"
            )
        imports[module_name] = str(module_path.relative_to(prefix))
    return imports


def _encode_probe(llama_dir: Path) -> dict[str, Any]:
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(llama_dir, local_files_only=True)
    text = "I need someone to listen, not advice."
    token_ids = tokenizer.encode(text, add_special_tokens=False)
    if not token_ids or tokenizer.decode(token_ids) != text:
        raise RuntimeError("Llama tokenizer probe did not round-trip exactly")
    return {
        "tokenizer_class": type(tokenizer).__name__,
        "probe_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "token_count": len(token_ids),
        "roundtrip_exact": True,
    }


def _embedding_probe(
    bge_dir: Path,
    *,
    require_cuda: bool,
    expected_dimension: int,
) -> dict[str, Any]:
    import torch
    from transformers import AutoModel, AutoTokenizer

    cuda_available = torch.cuda.is_available()
    if require_cuda and not cuda_available:
        raise RuntimeError("CUDA was required but torch.cuda.is_available() is false")
    device = "cuda" if cuda_available else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(bge_dir, local_files_only=True)
    model = AutoModel.from_pretrained(bge_dir, local_files_only=True).to(device).eval()
    texts = ["query about feeling overwhelmed", "a supportive reflection"]
    batch = tokenizer(
        texts, padding=True, truncation=True, return_tensors="pt"
    ).to(device)
    with torch.inference_mode():
        vectors = model(**batch).last_hidden_state[:, 0]
        vectors = torch.nn.functional.normalize(vectors, p=2, dim=1)
    expected_shape = (2, expected_dimension)
    if tuple(vectors.shape) != expected_shape:
        raise RuntimeError(f"unexpected BGE probe shape: {tuple(vectors.shape)}")
    norms = vectors.norm(dim=1).detach().cpu().tolist()
    if any(abs(value - 1.0) > 1e-5 for value in norms):
        raise RuntimeError(f"BGE normalized-vector probe failed: {norms}")
    cosine = float((vectors[0] @ vectors[1]).detach().cpu())
    return {
        "model_class": type(model).__name__,
        "device": device,
        "shape": [2, expected_dimension],
        "normalized": True,
        "cosine_diagnostic": round(cosine, 6),
        "torch_version": torch.__version__,
        "torch_cuda_version": torch.version.cuda,
        "cuda_available": cuda_available,
        "gpu_name": torch.cuda.get_device_name(0) if cuda_available else None,
    }


def build_attestation(args: argparse.Namespace) -> dict[str, Any]:
    if sys.version_info[:2] != (3, 11):
        raise RuntimeError(f"Paper-1 runtime requires Python 3.11, got {sys.version}")
    package_versions = verify_locked_environment(args.lock_file)
    import_paths = verify_import_boundary()
    llama_hashes = verify_files(args.llama_tokenizer_dir, LLAMA_FILES)
    bge_hashes = verify_files(args.bge_small_dir, BGE_FILES)
    bge_m3_hashes = verify_files(args.bge_m3_dir, BGE_M3_FILES)
    tokenizer_probe = _encode_probe(args.llama_tokenizer_dir)
    embedding_probe = _embedding_probe(
        args.bge_small_dir,
        require_cuda=args.require_cuda,
        expected_dimension=384,
    )
    bge_m3_probe = _embedding_probe(
        args.bge_m3_dir,
        require_cuda=args.require_cuda,
        expected_dimension=1024,
    )
    return {
        "protocol": PROTOCOL,
        "status": STATUS,
        "research_freeze_effect": "NONE_ZERO_OUTCOME_ENGINEERING_PREFLIGHT_ONLY",
        "outcome_calls": 0,
        "environment_name": Path(sys.prefix).name,
        "attestation_inputs": {
            "environment_file_sha256": _sha256(args.environment_file),
            "lock_file_sha256": _sha256(args.lock_file),
            "attestation_script_sha256": _sha256(Path(__file__).resolve()),
        },
        "python": {
            "major_minor": "3.11",
            "full_version": sys.version.split()[0],
            "user_site_enabled": site.ENABLE_USER_SITE,
            "python_no_user_site": os.environ.get("PYTHONNOUSERSITE"),
        },
        "generator": {
            "provider": "NVIDIA_hosted_NIM",
            "model": "meta/llama-3.1-8b-instruct",
            "local_install_role": "NONE_HOSTED_GENERATOR_NOT_LOCAL_TOKENIZER",
            "paper1_full_stack_manifest": "PENDING_M2_FREEZE",
        },
        "locked_packages": package_versions,
        "import_paths_relative_to_environment_prefix": import_paths,
        "llama_tokenizer_candidate": {
            "role": "LOCAL_TOKEN_ACCOUNTING_AND_CAP_CANDIDATE_NOT_GENERATOR",
            "repo": LLAMA_REPO,
            "revision": LLAMA_REVISION,
            "files": llama_hashes,
            "probe": tokenizer_probe,
            "nvidia_nim_provider_parity": "PENDING_M2_FREEZE",
        },
        "bge_small_encoder_candidate": {
            "role": "RS_LIGHTWEIGHT_CHALLENGER_AND_ENGINEERING_SMOKE_NOT_RETRIEVER_FREEZE",
            "repo": BGE_REPO,
            "revision": BGE_REVISION,
            "files": bge_hashes,
            "probe": embedding_probe,
        },
        "bge_m3_encoder_candidate": {
            "role": "OFFICIAL_RAG_MODEL_ID_AND_TYPED_MEMORY_CANDIDATE_NOT_RETRIEVER_FREEZE",
            "repo": BGE_M3_REPO,
            "revision": BGE_M3_REVISION,
            "files": bge_m3_hashes,
            "probe": bge_m3_probe,
            "official_es_memeval_binding": {
                "repository_commit": "692624208acc077b8867698c1d6fcd998dee641a",
                "model_id": "BAAI/bge-m3",
                "store": "FAISS",
                "session_level_top_k": 4,
                "revision_in_official_source": None,
                "official_main_revision_observed": "5617a9f61b028005a4858fdac845db406aefb181",
                "local_revision_role": "PUBLIC_SAFETENSORS_CONVERSION_REVISION_FOR_SAFE_LOCAL_RUNTIME",
                "config_bytes_match_official_main": True,
                "local_revision_parity_status": "MODEL_ID_AND_CONFIG_MATCH_OFFICIAL_WEIGHTS_AND_RUNTIME_CONTRACT_REQUIRE_M2_RECONCILIATION",
            },
        },
        "pending_researcher_freeze": [
            "nvidia_nim_provider_tokenizer_parity",
            "resource_renderer_and_token_cap",
            "retriever_encoder_and_revision",
            "official_bge_m3_local_revision_parity",
            "embedding_pooling_query_and_normalization_contract",
            "final_feature_schema",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    project_root = Path(__file__).resolve().parents[2]
    parser.add_argument(
        "--environment-file",
        type=Path,
        default=project_root / "environments/paper1-py311.yml",
    )
    parser.add_argument(
        "--lock-file",
        type=Path,
        default=project_root / "environments/requirements-paper1-py311.lock.txt",
    )
    parser.add_argument("--llama-tokenizer-dir", type=Path, required=True)
    parser.add_argument("--bge-small-dir", type=Path, required=True)
    parser.add_argument("--bge-m3-dir", type=Path, required=True)
    parser.add_argument("--require-cuda", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = build_attestation(args)
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
