# Payment Execution Finality — Reference Implementation

Runnable, vendor-neutral reference implementation of digest-bound, evidence-backed, consume-once authority for agentic and API-originated payments.

This repository implements the architecture described in **`draft-das-payment-execution-finality-00`**, *A Signed Instruction Is Not Settlement: Finality for Agentic and API Payments* by Sangam Das.

> Payment rails authenticate and transport instructions. This implementation asks a separate last-mile question: may this exact amount, currency, beneficiary, account, purpose and rail become effective at this settlement sink now?

## What is implemented

The executable path is:

```text
ERP / model / API / agent
        |
        v
Payment Candidate Act (NON_EFFECTIVE)
        |
        v
Protected Enforcement Domain (PED)
  - normalizes money
  - computes instruction digest
  - validates mandate, payee, rail, purpose and epochs
  - commits signed validation evidence
  - issues scoped non-bearer authority
        |
        v
Settlement Sink
  - verifies evidence and authority integrity
  - recomputes digest from live instruction
  - checks amount, currency, beneficiary, rail and purpose
  - checks sink, holder, expiry and live epochs
  - atomically reserves consume-once state
        |
        +-- PASS: post once; mark POSTED
        |
        `-- FAIL: no rail call and no balance-changing effect
```

The implementation contains:

- a strict load-bearing instruction projection and deterministic SHA-256 digest;
- currency-aware decimal normalization without binary floating point;
- candidate acts that remain `NON_EFFECTIVE` until sink admission;
- PED policy validation and evidence-before-authority ordering;
- HMAC-protected evidence and authority objects behind a replaceable authenticator interface;
- binding to exact digest, amount, currency, beneficiary account, rail, purpose, nonce, epochs, sink, agent and workload;
- a durable SQLite consume state machine: `UNUSED → CONSUMED_PENDING → POSTED`;
- duplicate-digest protection across separately issued authorities;
- explicit handling of definite and uncertain rail failures;
- a simulated rail adapter that makes tests safe to run;
- 52 tests covering success, substitution, expiry, revocation, replay, concurrent consume, failures and canonicalization;
- benchmark tooling reporting p50, p95 and p99 by stage;
- GitHub Actions across Python 3.10–3.13;
- deterministic cross-language test material and porting rules.

## Repository status

This is an **engineering reference**, not a payment product, bank core, certified HSM integration, or regulatory-compliance claim. The HMAC key, in-memory policy and simulated rail make the control flow inspectable. Production deployments must replace them with appropriate trust anchors, durable distributed state, protected key custody, rail integration and operations controls.

## Quick start

Python 3.10 or newer is required. The runtime has no third-party dependencies.

```bash
python -m pip install -e .
payment-finality-demo
python -m unittest discover -s tests -v
payment-finality-benchmark --iterations 1000 --warmup 100
```

Expected demo property: one authority produces one settlement reference and its durable state becomes `POSTED`. A second use is rejected before the rail adapter is called.

## Minimal integration

```python
from payment_finality import (
    HMACAuthenticator, InMemoryPolicy, InMemoryRail,
    PaymentInstruction, PolicySnapshot, ProtectedEnforcementDomain,
    SQLiteFinalityStore, SettlementSink,
)

snapshot = PolicySnapshot(policy_epoch=12, revocation_epoch=4, risk_list_epoch=7)
policy = InMemoryPolicy(
    snapshot=snapshot,
    permitted_rails={"SEPA_INSTANT"},
    permitted_purposes={"invoice-pay"},
    mandates={"mandate-vendors": {"vendor-441"}},
    hot_ceiling_by_currency={"EUR": "500.00"},
)
store = SQLiteFinalityStore("finality.db")
auth = HMACAuthenticator(b"replace-with-32-byte-or-longer-secret")
rail = InMemoryRail()

ped = ProtectedEnforcementDomain(policy, store, auth, ttl_seconds=10)
sink = SettlementSink(
    "core-post-eu-1", store, auth, rail,
    current_policy=lambda: policy.snapshot,
)

instruction = PaymentInstruction(
    act_type="INSTANT_CREDIT",
    payer_id="enterprise-7",
    payer_account_ref="acct-payer-1",
    amount="150",
    currency="EUR",
    beneficiary_id="vendor-441",
    beneficiary_account_ref="acct-vendor-441",
    rail_id="SEPA_INSTANT",
    purpose_id="invoice-pay",
    sink_id="core-post-eu-1",
    mandate_id="mandate-vendors",
    invoice_ref="INV-2026-441",
    agent_id="ap-agent-1",
    workload_id="spiffe://example/ap-agent/1",
)

candidate = ped.prepare(instruction)                    # still NON_EFFECTIVE
evidence, authority = ped.validate_and_issue(candidate) # evidence committed first
settlement_ref = sink.verify_and_post(instruction, authority)
```

In a real integration, only the sink component may hold the route to the PSP SDK, clearing release function, ledger mutation, card capture, CBDC engine or core-post API. If another callable path can post without this check, that alternate path remains outside the protected boundary.

## Load-bearing fields

The reference digest includes:

| Class | Fields |
|---|---|
| Act | `act_type` |
| Payer/holder | payer ID, payer account reference, agent ID, workload ID |
| Value | normalized amount, uppercase currency |
| Beneficiary | beneficiary ID, account reference, jurisdiction |
| Rail | rail ID |
| Purpose | purpose ID, mandate ID, invoice reference, end-to-end ID |

`metadata` is intentionally excluded and tested as non-load-bearing. Production extensions must explicitly classify every new field. A field that can change the economic or jurisdictional meaning belongs in the digest.

## Non-bearer meaning in this implementation

The authority object is not accepted merely because it is possessed. Its integrity is necessary but insufficient. The sink also requires matching:

- live instruction digest;
- exact settlement sink;
- current policy, revocation and risk-list epochs;
- agent ID and workload ID;
- unused nonce and authority state;
- committed validation evidence;
- unexpired lifetime.

Copying the object to another sink, worker, beneficiary, rail, epoch or instruction does not authorize a post.

## Consume and post semantics

`SQLiteFinalityStore.reserve()` uses `BEGIN IMMEDIATE` and a conditional state update. A unique partial index also prevents a second authority for the same instruction digest from becoming consumed or posted.

The state machine is:

| State | Meaning | Retry behavior |
|---|---|---|
| `UNUSED` | Authority registered but not admitted | May be presented until expiry/epoch change |
| `CONSUMED_PENDING` | Sink reserved authority; rail outcome not yet durably completed | Do not resubmit blindly; reconcile |
| `POSTED` | Settlement reference recorded | Return prior outcome or deny repeat; never post again |
| `FAILED_DEFINITE` | Rail confirmed no external effect | Original authority stays terminal; revalidate and issue a new act if policy permits |

An external HTTP payment cannot generally be made atomically with a local SQLite transaction. This implementation therefore reserves first and fails closed on an uncertain result. Production patterns are described in [Deployment and system variations](docs/SYSTEM_VARIATIONS.md).

## Latency target

The Internet-Draft gives a representative target of **about 1–10 ms added hot-path latency** for local policy and a local consume table. It is not a protocol constant or a universal SLA.

The included benchmark measures three local software stages separately:

1. candidate preparation and digest;
2. PED validation, evidence commit and authority issue;
3. sink verification, durable consume and simulated post.

On the build environment used for this release, 1,000 measured operations after 100 warmups produced:

| Stage | p50 | p95 | p99 |
|---|---:|---:|---:|
| Prepare | 0.0316 ms | 0.0683 ms | 0.0984 ms |
| PED issue | 0.1648 ms | 0.3214 ms | 0.7665 ms |
| Sink verify/consume/simulated post | 0.1395 ms | 0.2614 ms | 0.4064 ms |
| Full local reference path | 0.3537 ms | 0.6486 ms | 1.2040 ms |

These values use in-process HMAC, in-memory SQLite and a simulated rail. They do **not** include HSM/KMS calls, durable network storage, cross-region consensus, sanctions or AML services, PSP latency, clearing, settlement, or human approval. Reproduce results on the intended deployment rather than using these numbers as a capacity commitment. See [Latency methodology](docs/LATENCY.md).

## System variations

The same bindings can be deployed in several forms:

| Variant | PED placement | Sink placement | State/key choice | Primary trade-off |
|---|---|---|---|---|
| Embedded core adapter | bank/core process | immediately before ledger post | core DB + HSM | strongest path closure; deepest integration |
| PSP cooperating sink | platform or PSP | PSP capture/payout endpoint | PSP consume store + KMS/HSM | protects multiple clients; requires PSP support |
| Enterprise sidecar | AP/TMS trust domain | in-line before PSP SDK | local HA DB + KMS | incremental pilot; alternate routes must be closed |
| Agent two-sink | agent authorization service | tool-dispatch sink plus payment-post sink | two scoped authorities or combined object | separates tool execution from value movement |
| Batch clearing | batch validation service | file release gate | row digest table or signed digest manifest | per-row scale and partial-failure handling |
| Card capture/refund | merchant/platform PED | acquirer-facing submitter | idempotency store plus finality state | acquirer uncertainty requires reconciliation |
| FX/split payment | pricing/risk PED | coordinated leg sinks | transaction coordinator or conditional legs | prevents partial economic effect |
| CBDC/on-us ledger | participant/ledger policy domain | balance-change function | ledger-native atomic consume | protocol-specific integration required |

See [System variations](docs/SYSTEM_VARIATIONS.md) for detailed trust and failure behavior.

The origin and status of every sample value—10-second TTL, EUR 500 ceiling, epochs, canonicalization, HMAC and SQLite—are listed in [Parameters and provenance](docs/PARAMETERS.md).

## Language variations

Python is used because it keeps the state machine readable. Equivalent implementations can be written in TypeScript, Go, Rust, Java/Kotlin, C# or another language if they preserve byte-level canonicalization, decimal rules, signature input, clock semantics and atomic consume behavior.

| Concern | Python reference | TypeScript | Go | Rust | Java/Kotlin |
|---|---|---|---|---|---|
| Money | `decimal.Decimal` | decimal library or integer minor units; never `number` | integer minor units or decimal package | fixed-point/decimal crate | `BigDecimal` with explicit scale |
| Canonical bytes | sorted compact UTF-8 JSON subset | RFC 8785/JCS library or identical serializer | canonical/JCS encoder | JCS/canonical serializer | JCS/canonical serializer |
| Constant-time MAC compare | `hmac.compare_digest` | `timingSafeEqual` | `hmac.Equal` | `subtle::ConstantTimeEq` | `MessageDigest.isEqual` |
| Consume CAS | SQLite transaction | SQL transaction/conditional update | SQL transaction/conditional update | SQL transaction/conditional update | transaction plus affected-row check |
| UTC time | aware `datetime` | `Temporal.Instant`/epoch milliseconds | `time.Time` UTC | `OffsetDateTime`/`Instant` | `Instant` |

Cross-language ports must pass the supplied canonical vector before interoperability claims. See [Language portability](docs/LANGUAGE_VARIANTS.md).

## Test coverage

The 52 tests include:

- amount normalization for 0-, 2- and 3-decimal currencies;
- malformed, zero, negative, non-finite and over-scale amounts;
- happy path and evidence-before-authority;
- amount, currency, beneficiary ID/account, rail, purpose, mandate, invoice, sink, agent and workload substitution;
- blocked payee, missing mandate and amount-envelope denial;
- policy, revocation and risk-list epoch changes;
- expired, tampered and missing-evidence authority;
- same-authority replay and second-authority/same-digest replay;
- concurrent double-submit with exactly one simulated post;
- definite rail failure and ambiguous rail timeout behavior;
- persistent SQLite reopen.

Run them with:

```bash
python -m unittest discover -s tests -v
```

## What is not implemented

- a real ISO 20022, SWIFT, ACH, SEPA, FedNow, card, CBDC or PSP adapter;
- an HSM, TEE, confidential-computing, remote-attestation or threshold-signature integration;
- distributed consensus or multi-region replay prevention;
- complete RFC 8785 JSON Canonicalization Scheme conformance;
- a production key lifecycle, certificate chain or key rotation protocol;
- sanctions, AML, SCA, PCI DSS, PSD2 or other compliance certification;
- automatic safe resolution of an externally ambiguous payment result;
- privacy-preserving account tokenization or encrypted evidence storage;
- a full agent-tool dispatch authority object from the companion agentic profile.

See [Limitations](docs/LIMITATIONS.md) and [Security](SECURITY.md) before adapting the code.

## Repository map

```text
src/payment_finality/
  canonical.py   explicit load-bearing projection and digest
  crypto.py      replaceable authenticator; reference HMAC
  models.py      candidate, evidence and authority objects
  policy.py      illustrative hot-envelope policy
  ped.py         prepare, validate, commit evidence, issue authority
  store.py       durable consume/post state machine
  sink.py        last-mile verification and rail admission
  rail.py        rail adapter interface and safe simulator
  demo.py        complete allow path
  benchmark.py   stage latency measurement
  tests/           52 executable tests
test-vectors/    deterministic canonicalization vector
schemas/         payment candidate JSON Schema
docs/            latency, system, language and limitation notes
```

## Relationship to existing payment controls

This profile is additive. ISO 20022 and clearing formats remain message/transport mechanisms. OAuth and API keys remain client authentication/authorization mechanisms. SCA/3-D Secure, mandates, risk screening, maker-checker and idempotency remain useful inputs or controls. None is treated by this implementation as a substitute for sink-side matching and consume-once authority over the exact live payment act.

## Intellectual-property and licensing notice

The source Internet-Draft states that concepts in the profile are associated with the DAS Protocols family, including International Application PCT/IB2026/055615, and that IETF disclosure should follow BCP 79. This repository does not independently determine patent scope, validity, essentiality or licensing terms.

No software license has been selected in this package. Before public reuse is invited, the repository owner should add the intended software license and, separately where relevant, a patent-license statement. A software copyright license and a patent license answer different questions.
