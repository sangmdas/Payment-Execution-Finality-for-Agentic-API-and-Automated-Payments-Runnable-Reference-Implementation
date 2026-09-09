# Latency targets and measurement

## Target classes

The profile's representative engineering targets are:

| Path | Intended behavior | Planning target |
|---|---|---:|
| Hot path | cached/local mandate and risk predicates; local digest, verify and consume | about 1–10 ms added |
| Warm remote path | same-region networked policy, HSM/KMS or strongly consistent store | commonly 5–50 ms; measure |
| Cold automated path | fresh beneficiary/country/risk evaluation or cross-region state | tens to hundreds of ms |
| Human/threshold path | checker approval or unavailable shares | unbounded by protocol; hold non-effective |
| Transparency anchor | external log, chain or audit publication | asynchronous; not on enable path |

Only the first and third descriptions come directly from the draft. The warm-path band is an implementation planning range, not a protocol requirement or measured promise.

## Illustrative hot-path budget

| Operation | Planning allocation |
|---|---:|
| Decode and structural validation | 0.05–0.50 ms |
| Money normalization and canonical digest | 0.02–0.25 ms |
| Authority/evidence verification | 0.02–5.00 ms depending on software vs HSM/network |
| Epoch and binding comparisons | 0.01–0.20 ms |
| Durable consume CAS | 0.20–4.00 ms depending on storage and contention |
| Local adapter dispatch | 0.05–1.00 ms before external rail time |

These are budget placeholders for load-test design. They are not measured constants.

## Benchmark methodology

`payment-finality-benchmark` uses a monotonic high-resolution clock and reports min, mean, p50, p95, p99 and max for:

- `prepare`;
- `ped_issue`;
- `sink_verify_consume_post`;
- `total`.

Every iteration has a unique invoice and end-to-end ID so digest-level replay protection does not turn the benchmark into a denial benchmark. Warmup samples are discarded. The rail adapter is in-process and does not move value.

```bash
payment-finality-benchmark --iterations 10000 --warmup 1000 > benchmark.json
```

## Production measurement requirements

Record at least:

- p50, p95, p99 and p99.9 by rail, region and amount envelope;
- policy/PED issue time separately from sink time;
- HSM/KMS verification time and error rate;
- consume-store latency, conflict rate and lock wait;
- denial latency by failure code;
- count and age of `CONSUMED_PENDING` rows;
- external rail response and reconciliation latency separately;
- cold-path and human-share time separately from the hot path.

Never improve availability by converting a PED, epoch, evidence or consume timeout into permission to post. A timeout is hold-or-deny.

## Interpreting the included result

The checked-in benchmark result is useful for regression detection in this codebase. It is not comparable to a deployment using a durable remote database, hardware key, networked risk engine or real rail. Hardware, operating-system scheduling, virtualization, storage settings, database durability and concurrency all change the result.

