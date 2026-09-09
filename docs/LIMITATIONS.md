# Limitations

## Security and trust

- `HMACAuthenticator` is a software reference using one shared secret. Compromise of that secret permits forged evidence and authority. Production should use isolated key custody and usually asymmetric verification at sinks.
- The PED is a Python process, not a hardware-protected or remotely attested domain.
- The agent host and sink are not isolated in the demo. Real deployments must prevent the agent from reaching the rail around the sink.
- There is no key rotation, certificate validation, algorithm negotiation or compromise-recovery protocol.

## Canonicalization and schemas

- `EF-JCS-SUBSET-1` sorts object keys and emits compact UTF-8 JSON, but it is not full RFC 8785 JCS for arbitrary JSON numbers or Unicode edge cases.
- The implementation controls its projection and represents money as strings, which narrows the risk but does not establish general JSON interoperability.
- The draft's candidate JSON Schema is included for reference, but runtime objects are Python dataclasses rather than a full JSON Schema validator.
- Currency scale coverage is illustrative. A production table must be sourced, versioned and tested for every supported currency/token/asset.

## Storage and distributed operation

- SQLite is appropriate for a demonstration or single-node pilot, not a multi-region global consume service.
- The unique digest constraint exists only inside one database. Independent sinks need a shared uniqueness domain or sink-specific authority that cannot be accepted elsewhere.
- Clock synchronization and secure time are assumed.
- Recovery, backup, replication, disaster recovery and database migration are not implemented.

## External rail atomicity

- A local database transaction cannot normally atomically commit an external PSP, acquirer or clearing action.
- The reference reserves authority before the call. An ambiguous timeout leaves `CONSUMED_PENDING` and requires reconciliation.
- The code does not implement provider-specific status lookup, idempotent replay, transactional outbox/inbox, ISO acknowledgment correlation or operator tooling.
- `FAILED_DEFINITE` depends on the adapter being able to prove no external effect occurred. Misclassifying an uncertain failure as definite can create duplicates.

## Payment coverage

- Only a single payment instruction is modeled. Batch manifests, threshold shares, FX two-leg atomicity, split payouts, refunds tied to originals and partial clearing outcomes are documentation-only variations.
- No real ISO 20022, ACH, SEPA, FedNow, SWIFT, card, open-banking, CBDC or ledger adapter is supplied.
- Legal settlement finality, reversals, chargebacks, returns and disputes are outside the state machine.

## Policy and compliance

- The policy is an in-memory allowlist/envelope example, not a fraud, AML, sanctions, SCA or mandate service.
- The repository does not establish compliance with PSD2/PSD3, PCI DSS, AML, sanctions, consumer protection, data protection or any local payment law.
- Regulatory screening may be a PED predicate but is not act-specific settlement authority by itself.

## Privacy

- Example account references are stored in plaintext SQLite/JSON.
- There is no encryption at rest, field tokenization, selective disclosure, retention schedule or data-subject workflow.
- Production authority objects leaving a posting host should prefer account digests or scoped tokens over raw account identifiers.

## Performance

- The checked-in benchmark is single-process and mostly single-threaded, using in-memory SQLite and a simulated rail.
- It does not measure HSM, KMS, database fsync over network storage, risk services, rail time, contention, failover or cross-region consensus.
- The 1–10 ms hot-path figure is a target class from the draft, not guaranteed by this repository.

## Scope and maturity

- This is not audited, formally verified, certified or production hardened.
- The reference demonstrates one interpretation of draft version `-00`; later draft revisions may change fields or requirements.
- Passing tests demonstrates these code paths, not the absence of all vulnerabilities or design-around paths.

