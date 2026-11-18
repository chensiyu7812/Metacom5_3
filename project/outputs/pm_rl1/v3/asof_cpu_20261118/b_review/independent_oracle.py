"""WS-B raw-JSON oracle; never imports the A materializer/filter implementation."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

REGISTRY = "project/outputs/pm_rl1/v3/A1_preparation/final/registry/sources.jsonl"
OWNERS = ("p1", "p15", "p18")


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compute(root):
    entries = [json.loads(line) for line in (root / REGISTRY).read_text().splitlines()]
    rows = []
    for owner in OWNERS:
        personal = sorted(
            (e for e in entries if e["availability_scope"] == "personal_history"
             and e["source"]["owner_id"] == owner),
            key=lambda e: e["source"]["chronological_rank"],
        )
        for current in personal[1:]:
            source = current["source"]
            cutoff = source["chronological_rank"]
            turns = source["turns"]
            cut_turn = next(
                i for i, turn in enumerate(turns[:-1])
                if turn["role"] == "seeker" and turns[i + 1]["role"] == "supporter"
            )
            expected = []
            for entry in entries:
                candidate = entry["source"]
                if (entry["availability_scope"] != "personal_history"
                    or candidate["dataset"] != source["dataset"]
                    or candidate["owner_id"] != owner
                    or not candidate["complete"]
                    or candidate["chronological_rank"] >= cutoff):
                    continue
                report = entry["reported_at"]
                ready = entry["ready_at"]
                if report is None or ready is None:
                    continue
                if report["session_rank"] >= cutoff or ready["session_rank"] > cutoff:
                    continue
                if any(point.get("date") and source["date"] and point["date"] > source["date"]
                       for point in (report, ready)):
                    continue
                if candidate["date"] and source["date"] and candidate["date"] > source["date"]:
                    continue
                expected.append({
                    "session_id": candidate["session_id"],
                    "owner_id": owner,
                    "rank": candidate["chronological_rank"],
                    "family_id": candidate["family_id"],
                    "transcript_sha256": candidate["transcript_sha256"],
                    "known_rank": report["session_rank"],
                    "ready_rank": ready["session_rank"],
                })
            expected.sort(key=lambda e: (e["rank"], e["session_id"]))
            rows.append({
                "owner_id": owner, "session_id": source["session_id"],
                "cutoff_rank": cutoff, "cut_turn": cut_turn,
                "prefix_last_quote": turns[cut_turn]["text"],
                "expected_sources": expected,
            })
    return {
        "protocol": "ws-b-raw-json-frontier-oracle-v1",
        "review_type": "independent_ai_engineering_review_not_human_semantic_approval",
        "source_file": REGISTRY, "source_file_sha256": file_sha(root / REGISTRY),
        "owners": list(OWNERS), "cut_count": len(rows), "cuts": rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    payload = compute(args.root)
    with args.out.open("x") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"cut_count": payload["cut_count"], "owners": payload["owners"]}))
