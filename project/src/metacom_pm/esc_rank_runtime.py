"""Fail-closed helpers for the V3 ESC-RANK runtime overlay.

The official ESC-RANK source and prompts remain the benchmark authority. This
module only supplies the path/revision/parser corrections required by the V3
measurement contract; it does not download or execute a model.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass


ESC_EVAL_COMMIT = "9ad46e7b5e247e824dae4633910eaa82be668beb"
ESC_RANK_REVISION = "450bf2eb5376c79e371aaf432925810243de1527"
ESC_ROLE_REVISION = "2e2a4733d2e71da242f348aad165fe171acd5df7"
INTERNLM2_REVISION = "c2ba64483dc50b3f8eb2d8271c4b9877a79ed2e2"
STRICT_ORDINAL_PATTERN = re.compile(r"^[0-4]$")


@dataclass(frozen=True)
class ESCRankRuntimeIdentity:
    esc_eval_commit: str = ESC_EVAL_COMMIT
    esc_rank_revision: str = ESC_RANK_REVISION
    esc_role_revision: str = ESC_ROLE_REVISION
    base_model: str = "internlm/internlm2-chat-7b"
    base_model_revision: str = INTERNLM2_REVISION
    dtype: str = "float16"
    decoding: str = "do_sample=false;temperature=0"
    parser: str = "full-string ordinal ^[0-4]$ or INVALID"

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def parse_strict_ordinal(raw: str) -> int | None:
    """Return an ordinal only when the complete trimmed output is 0..4."""

    normalized = raw.strip()
    if STRICT_ORDINAL_PATTERN.fullmatch(normalized) is None:
        return None
    return int(normalized)


def repair_official_adapter_paths(source: str) -> str:
    """Repair only the two published ESC-RANK1 fluency path defects."""

    expected = {
        '"./ESC-RANK1/fluency"': 1,
        '"./ESC-RANK1/fluency_en"': 1,
    }
    for token, count in expected.items():
        observed = source.count(token)
        if observed != count:
            raise ValueError(f"expected {count} occurrence of {token}, found {observed}")
    repaired = source.replace('"./ESC-RANK1/fluency"', '"./ESC-RANK/fluency"')
    repaired = repaired.replace('"./ESC-RANK1/fluency_en"', '"./ESC-RANK/fluency_en"')
    if "ESC-RANK1" in repaired:
        raise ValueError("unexpected ESC-RANK1 path remains after bounded repair")
    return repaired
