from __future__ import annotations

import argparse
import json
import platform
import sqlite3
import statistics
import time

from .demo import build_demo, sample_instruction
from .models import PaymentInstruction


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * p)))
    return ordered[index]


def stats(values_ns: list[int]) -> dict[str, float]:
    values = [v / 1_000_000 for v in values_ns]
    return {
        "min_ms": round(min(values), 4),
        "mean_ms": round(statistics.fmean(values), 4),
        "p50_ms": round(percentile(values, 0.50), 4),
        "p95_ms": round(percentile(values, 0.95), 4),
        "p99_ms": round(percentile(values, 0.99), 4),
        "max_ms": round(max(values), 4),
    }


def run(iterations: int, warmup: int) -> dict:
    _, _, ped, sink, _ = build_demo()
    samples = {"prepare": [], "ped_issue": [], "sink_verify_consume_post": [], "total": []}
    for i in range(iterations + warmup):
        base = sample_instruction()
        instruction = PaymentInstruction(**{
            **base.__dict__,
            "invoice_ref": f"INV-BENCH-{i}",
            "end_to_end_id": f"E2E-BENCH-{i}",
        })
        total_start = time.perf_counter_ns()
        start = total_start
        act = ped.prepare(instruction)
        prepare_end = time.perf_counter_ns()
        _, authority = ped.validate_and_issue(act)
        issue_end = time.perf_counter_ns()
        sink.verify_and_post(instruction, authority)
        sink_end = time.perf_counter_ns()
        if i >= warmup:
            samples["prepare"].append(prepare_end - start)
            samples["ped_issue"].append(issue_end - prepare_end)
            samples["sink_verify_consume_post"].append(sink_end - issue_end)
            samples["total"].append(sink_end - total_start)
    return {
        "warning": "Illustrative local software benchmark; not a payment-rail, HSM, KMS, or network SLA.",
        "target": {"added_hot_path_ms": "1-10", "source": "draft-das-payment-execution-finality-00"},
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "sqlite": sqlite3.sqlite_version,
            "store": "SQLite :memory:",
            "authenticator": "HMAC-SHA-256 software reference",
            "rail": "in-process simulated rail",
        },
        "iterations": iterations,
        "warmup": warmup,
        "results": {name: stats(values) for name, values in samples.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--warmup", type=int, default=100)
    parser.add_argument("--output", choices=("json", "text"), default="json")
    args = parser.parse_args()
    if args.iterations < 1 or args.warmup < 0:
        parser.error("iterations must be positive and warmup non-negative")
    result = run(args.iterations, args.warmup)
    print(json.dumps(result, indent=2) if args.output == "json" else result)


if __name__ == "__main__":
    main()

