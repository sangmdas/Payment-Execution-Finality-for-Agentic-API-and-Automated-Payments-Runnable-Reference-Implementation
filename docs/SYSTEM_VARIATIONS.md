# Deployment and system variations

The invariant is placement, not product naming: the sink is the last component whose refusal makes the covered external effect technically non-completable on that path.

## 1. Embedded bank-core adapter

- PED: bank policy/authorization service.
- Sink: transaction boundary immediately before debit/ledger post and clearing release.
- Authority protection: asymmetric signature or HSM MAC.
- Consume: same database transaction as the ledger mutation when possible.
- Advantage: strongest atomicity and alternate-path control.
- Limitation: integration and certification cost; legacy posting paths must be inventoried.

## 2. Enterprise sidecar before a PSP SDK

- PED: enterprise AP/TMS authorization service.
- Sink: in-line service owning the only egress credential and network route to the PSP.
- Consume: HA relational database or strongly consistent key/value CAS.
- Advantage: practical pilot without replacing a core or rail.
- Limitation: it is not non-bypassable if another host, file drop, UI or credential can reach the PSP.

The sidecar must own or mediate egress. Merely wrapping one application function while leaving the raw PSP client reachable is an integration convention, not finality.

## 3. PSP as cooperating sink

- Platform creates the Candidate Act and obtains authority.
- PSP independently verifies the attached object/header immediately before capture/payout.
- PSP consumes authority in its idempotency/transaction store.
- Advantage: reuse across many platform clients and better control of ambiguous results.
- Limitation: trust, schema and key federation between platform and PSP are required.

## 4. Agent tool dispatch plus payment settlement

An agent-originated payment has two distinct effects:

1. dispatch of `payout.create` or equivalent;
2. movement of value at the posting sink.

Use either two independently scoped authorities or a combined object that satisfies both profiles. The tool dispatcher cannot substitute for the posting sink, and the posting sink cannot prevent every unintended non-payment tool side effect.

## 5. Batch ACH, payroll or clearing file

Treat each row as its own Candidate Act, or use an envelope that commits the ordered set of row digests, total amount, row count, file purpose, rail and sink. File signature and filename are not per-row consume authority.

Operational choices:

- all-or-nothing file admission;
- individually consumable rows with a signed manifest;
- chunked Merkle manifests for very large batches.

The current reference implements individual acts, not manifests or Merkle proofs.

## 6. Card capture and refund

Capture, refund and reversal are different `act_type` values. Bind merchant/sub-merchant, amount, currency, order, acquiring route and sink. Treat 3-D Secure/SCA evidence as PED input, not permission to skip consume.

If the acquirer call times out after transmission, leave the authority `CONSUMED_PENDING` and query by the provider's idempotency/reference key. Do not issue a replacement authority until the prior economic outcome is resolved.

## 7. Instant payment

Keep beneficiary, currency, rail, ceiling, purpose, sink and epochs in a locally cached bounded envelope. Every individual payment still receives a fresh nonce, exact digest and consume operation. Hot means cached predicates, not skipped finality checks.

## 8. FX and split legs

Either:

- one act commits both debit and credit legs, currencies, amount/rate or rate-source epoch, jurisdiction and coordinated sinks; or
- separate acts are linked by a coordinator that prevents unilateral completion when the business meaning requires both legs.

The current single-leg reference does not implement atomic cross-sink settlement.

## 9. CBDC, stored value or on-us book

Place verification directly before the balance mutation. When the ledger can atomically consume authority and update balances, atomicity is stronger than an external PSP adapter. CBDC-specific privacy, offline, consensus and legal-finality rules remain outside this repository.

## 10. Key and evidence variations

| Assurance level | Authority protection | Evidence store | Consume store |
|---|---|---|---|
| Demonstration | process HMAC | SQLite | SQLite |
| Enterprise | KMS/HSM asymmetric signature | append-protected database | HA relational CAS |
| High assurance | HSM/TEE-attested signing service | tamper-evident/WORM plus online index | ledger-native or strongly consistent quorum |
| Multi-organization | federated certificates/threshold authorization | independently verifiable evidence | sink-owned global uniqueness domain |

Evidence may later be anchored to an external transparency service, but the anchor must not retroactively authorize an act. The sink needs resolvable, protected evidence on the enable path.

## Alternate-path closure checklist

- List every API, UI, batch/file, scheduler, support tool and recovery procedure that can cause the same debit/release.
- Identify the true posting function for each path.
- Move credentials/network access so every covered path crosses a verifying sink.
- Deny or hold when authority, evidence, epoch or consume state is unavailable.
- Track ungated legacy paths with an owner and closure date.

