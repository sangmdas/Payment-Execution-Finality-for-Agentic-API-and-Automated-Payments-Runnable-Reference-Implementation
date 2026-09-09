# Parameters and provenance

This file separates profile-derived values from reference-only engineering choices. That distinction prevents a sample value from being mistaken for a protocol constant.

## Payment and authority parameters

| Parameter | Reference value | Source/reason | Production rule |
|---|---|---|---|
| Candidate status | `NON_EFFECTIVE` | Required architecture state | Preserve until sink admission |
| Digest | SHA-256, base64url no padding | Draft permits SHA-256/384/512; SHA-256 selected for reference | Version algorithm and encoding |
| Canonicalization | `EF-JCS-SUBSET-1` | Readable deterministic subset; draft recommends JCS or declared stable form | Prefer full RFC 8785 JCS for open interoperability |
| Amount representation | decimal string | Draft recommends strings to avoid float drift | Never use binary float |
| Currency scale | EUR/USD/INR/GBP=2, JPY/CLP=0, KWD/BHD/OMR=3 | Illustrative common-currency table | Replace with authoritative, versioned rail table |
| Authority TTL | 10 seconds | Matches the draft's worked authority timestamps and short-TTL principle | Select by rail/risk; measure clock and queue behavior |
| Single use | `true` | Required consume-once behavior | Do not make optional on financial acts |
| Hot ceiling | EUR 500.00 | Draft's worked hot-envelope example | Policy input, never a universal default |
| Permitted rail | `SEPA_INSTANT` | Worked example | Configure per account, purpose and jurisdiction |
| Purpose | `invoice-pay` | Worked example | Bind exact controlled purpose ID |
| Sink | `core-post-eu-1` | Worked example | Use stable identifier for actual posting boundary |
| Policy epoch | 12 | Worked example | Monotonic policy-controlled value |
| Revocation epoch | 4 | Worked example | Advance on relevant revocation |
| Risk-list epoch | 7 | Reference addition exercising draft requirement | Advance on material beneficiary/risk-list change |

## Reference implementation choices

| Choice | Why used here | Why it is not production guidance |
|---|---|---|
| Python 3.10+ | concise, inspectable state machine; standard-library support | runtime selection depends on target platform |
| HMAC-SHA-256 | deterministic, portable authenticator interface | shared secret and process memory are weaker than isolated signing custody |
| 32-byte minimum HMAC key | reasonable floor for the demonstration | production keys require generated entropy, lifecycle and rotation |
| SQLite | shows durable schema, transaction and conditional consume | not a global multi-region uniqueness service |
| `BEGIN IMMEDIATE` | serializes competing consume attempts in SQLite | other databases need equivalent CAS/locking semantics, not this exact SQL |
| In-memory rail | makes tests non-effecting and deterministic | provides no real PSP/clearing semantics |
| Unknown rail result → `CONSUMED_PENDING` | prevents blind replay after timeout | requires provider-specific reconciliation not included here |
| Metadata excluded from digest | demonstrates explicit non-load-bearing extension area | any consequence-bearing extension must be promoted into the digest projection |

## Environment reported by benchmark

The benchmark records Python implementation/version, operating-system platform, SQLite version, store mode, authenticator type and rail type in every JSON result. A production report should additionally record CPU, memory, container limits, database durability/replication, key-service topology, concurrency, payload sizes and rail adapter behavior.

## Changing a parameter safely

1. Decide whether it changes the logical act, wire representation, trust boundary or only local policy.
2. If it changes canonical bytes, create a new profile/canonicalization version and new vectors.
3. Add positive, mismatch, boundary, replay and concurrency tests.
4. Measure p50/p95/p99 under target durability and contention.
5. Document migration behavior for unused and `CONSUMED_PENDING` authorities.
6. Never silently relax an old verifier to accept both meanings under the same version.

