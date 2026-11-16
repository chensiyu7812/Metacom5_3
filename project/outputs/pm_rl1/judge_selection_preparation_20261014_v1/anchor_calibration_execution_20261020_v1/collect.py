"""Read-only closeout of the authorized run; never calls a model or account."""
import csv
from decimal import Decimal
from io import StringIO
import json
import os
from pathlib import Path
import time
import launch as live
from deepseek_access import cost_from_usage


def collect():
    protocol, _ = live.a.load()
    s, root = live.s, live.ROOT
    starts, results = live.p.replay(root, protocol)
    stop = s.read(root / "STOP.json") if (root / "STOP.json").exists() else None
    rows = []
    final_texts = []
    for slot in protocol["schedule"]:
        sid = slot["slot_id"]
        result = results.get(sid)
        raw = s.read(root / (sid + ".response.json")) if (root / (sid + ".response.json")).exists() else None
        ev = result.get("evaluation", {}) if result else {}
        financial = result.get("financial", {}) if result else {}
        usage = raw.get("usage", {}) if raw else {}
        final = raw.get("choices", [{}])[0].get("message", {}).get("content") if raw else None
        row = dict(
            position=slot["position"], target=slot["target_id"], arm=slot["arm"], draw=slot["draw"],
            slot_id=sid, started=sid in starts, state=(
                "completed" if result and result["technical_valid"] else "failed" if result
                else "started_unresolved" if sid in starts else "not_dispatched"),
            not_dispatched_reason=stop["reason"] if sid not in starts and stop else None,
            q=ev.get("q"), m=ev.get("m"), U=ev.get("U"),
            technical_valid=result.get("technical_valid") if result else None,
            model_unknown=ev.get("model_unknown"), technical_error=ev.get("error"),
            final_sha256=__import__("hashlib").sha256(final.encode()).hexdigest() if final is not None else None,
            request_identity=result.get("request_identity") if result else starts.get(sid, {}).get("request_identity"),
            input_payload_identity=slot["payload_identity"],
            semantic_revisions_applied=result.get("semantic_revisions_applied") if result else None,
            elapsed_seconds=result.get("elapsed_seconds") if result else None,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens_including_thinking=usage.get("completion_tokens"),
            reasoning_tokens_subset=usage.get("completion_tokens_details", {}).get("reasoning_tokens"),
            final_tokens_by_provider_difference=(
                usage["completion_tokens"] - usage["completion_tokens_details"]["reasoning_tokens"]
                if type(usage.get("completion_tokens")) is int and
                type(usage.get("completion_tokens_details", {}).get("reasoning_tokens")) is int else None),
            financial=financial,
            usage_price=cost_from_usage(raw) if raw else None,
            result_path=str(root / (sid + ".result.json")) if result else None,
            response_path=str(root / (sid + ".response.json")) if raw else None,
            reward_eligible=False)
        rows.append(row)
        final_texts.append(f"## {slot['position']:02} · {slot['target_id']} · {slot['arm']} · draw {slot['draw']}\n\n"
                           f"状态：{row['state']}；q/m/U：{row['q']} / {row['m']} / {row['U']}\n\n"
                           f"request_id: `{row['request_identity']}`\n\n"
                           f"final SHA256: `{row['final_sha256']}`\n\n"
                           "```json\n" + (final if final is not None else "未取得完整final") + "\n```\n")
    arms = {}
    for arm in ("baseline", "calibrated"):
        group = [r for r in rows if r["arm"] == arm]
        arms[arm] = dict(
            planned=len(group), started=sum(r["started"] for r in group),
            technical_valid=sum(r["technical_valid"] is True for r in group),
            numeric=sum(r["q"] is not None and r["m"] is not None for r in group),
            model_unknown=sum(r["model_unknown"] is True for r in group),
            prompt_tokens=sum(r["prompt_tokens"] or 0 for r in group),
            completion_tokens_including_thinking=sum(r["completion_tokens_including_thinking"] or 0 for r in group),
            reasoning_tokens_subset=sum(r["reasoning_tokens_subset"] or 0 for r in group),
            final_tokens_by_provider_difference=sum(r["final_tokens_by_provider_difference"] or 0 for r in group),
            request_seconds=sum(r["elapsed_seconds"] or 0 for r in group),
            accounted_upper_usd=str(sum((Decimal(r["financial"].get("accounted_upper_usd") or "0")
                                         for r in group), Decimal(0))),
            usage_price_estimate_usd=str(sum((Decimal((r["usage_price"] or {}).get("usage_price_estimate_usd") or "0")
                                             for r in group), Decimal(0))))
    out = live.BASE / "anchor_calibration_results_20261020_v1"
    out.mkdir(mode=0o700, exist_ok=False)
    uncompleted = len(starts) - len(results)
    unresolved = sum(s.nanodollars(r["financial"].get("unsettled_reservation_usd") or "0")
                     for r in rows) + uncompleted * live.p.RESERVE
    answer = dict(
        collected_unix=time.time(), study=live.a.STUDY, protocol_identity=protocol["identity"],
        historical_baseline=live.historical_count(), actual_new_attempts=len(starts),
        cumulative=live.historical_count() + len(starts), stage_hard_cap=225, capacity=289,
        planned_slots=24, distinct_responses=10, contexts=5, owners=3, independent_validation_cases=0,
        arms=arms, slots=rows, stop=stop, unresolved_liability_usd=s.usd(unresolved),
        financial_closeout=s.read(root / "financial_closeout.json") if (root / "financial_closeout.json").exists() else None,
        management_attempts={route: int((root / "management" / (stem + ".started.json")).exists())
                             for route, stem in [("models", "models"), ("user/balance", "user_balance")]},
        original_stops_unchanged=True, generator_calls=0, local_GPU_used=False,
        natural_RL_updates=0, reward_eligible=False, no_extra_human_judgments=True,
        semantic_review="Separate analyst source audit; not independent human labels.")
    s.save(out / "RESULTS.json", answer)
    stream = StringIO()
    fields = ["position", "target", "arm", "draw", "state", "q", "m", "U", "model_unknown",
              "elapsed_seconds", "prompt_tokens", "completion_tokens_including_thinking",
              "reasoning_tokens_subset", "final_tokens_by_provider_difference",
              "semantic_revisions_applied", "request_identity", "final_sha256", "not_dispatched_reason"]
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    (out / "SLOTS.csv").write_text(stream.getvalue())
    (out / "FINAL_OUTPUTS_EN.md").write_text(
        "# 本轮全部完整 final（原样）\n\n仅呈现已完成消息的content；不从thinking提取答案。"
        "q/m/U来自原校验结果，未改分。完整原响应、usage与SSE仍保存在执行目录。\n\n"
        + "\n".join(final_texts))
    print(s.canonical({k: answer[k] for k in (
        "actual_new_attempts", "cumulative", "arms", "stop", "unresolved_liability_usd", "financial_closeout")}))


if __name__ == "__main__":
    os.umask(0o077)
    collect()
