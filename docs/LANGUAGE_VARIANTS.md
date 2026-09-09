# Cross-language implementation guidance

An implementation is interoperable only when it creates the same canonical bytes and digest, verifies the same signed structure, and enforces the same state transitions.

## Mandatory invariants

Every port must preserve:

1. UTF-8 encoding with no locale-dependent conversion.
2. Decimal normalization before hashing; never binary floating point for money.
3. A declared currency scale table and rejection of excess scale.
4. An explicit load-bearing projection; never hash an arbitrary application object.
5. Deterministic key ordering and compact JSON or full RFC 8785/JCS.
6. Signature/MAC over the unsigned object only.
7. Constant-time authentication-tag comparison.
8. UTC, timezone-aware expiry with `now >= expires_at` treated as expired.
9. Conditional `UNUSED → CONSUMED_PENDING` transition with exactly one winner.
10. Fail-closed behavior on missing evidence, stale epochs, storage timeout or uncertain rail outcome.

## Python

- Use `Decimal`, not `float`.
- Use aware UTC `datetime` values.
- Use `hmac.compare_digest` for MACs.
- The included `json.dumps(..., sort_keys=True, separators=(",", ":"))` is only the repository's restricted subset, not complete JCS.

## TypeScript/JavaScript

- Do not store payment amounts in `number`.
- Use integer minor units or a decimal library with an explicit currency scale.
- Do not rely on ordinary `JSON.stringify` property insertion order for protocol canonicalization; use a reviewed JCS implementation or reproduce the supplied projection and ordering exactly.
- Use `crypto.timingSafeEqual` after validating equal tag lengths.
- Use a SQL transaction with `UPDATE ... WHERE state='UNUSED'` and require affected rows to equal one.

## Go

- Prefer integer minor units when all rails have fixed scale; otherwise use a reviewed decimal type.
- Do not use default map serialization as a protocol assumption. Use a canonical encoder.
- Use `hmac.Equal`.
- Keep `time.Time` in UTC and strip monotonic components before wire encoding.
- Treat SQL affected-row count other than one as denial.

## Rust

- Use fixed-point/integer minor units or a decimal crate; reject implicit rounding.
- Use a JCS/canonical JSON crate or explicit serialized structs.
- Use constant-time equality for tags.
- Model authority state as an enum and require a compare-and-swap transition in storage.
- Do not let `Result` fallback branches turn verification errors into post attempts.

## Java/Kotlin

- Use `BigDecimal`; call `setScale(expected, RoundingMode.UNNECESSARY)` to reject excess precision.
- Use `Instant` for TTL and epoch comparisons.
- Configure a deterministic canonical JSON implementation; ordinary mapper settings are not sufficient unless locked and tested.
- Use `MessageDigest.isEqual` for tag comparison.
- Use a transaction and an affected-row check for consume.

## C#/.NET

- Use `decimal` only within its precision envelope; use integer minor units or arbitrary-precision decimal for broader rails.
- Use `DateTimeOffset`/UTC or `Instant`-equivalent time.
- Use `CryptographicOperations.FixedTimeEquals`.
- Use a deterministic canonical JSON writer and optimistic concurrency token/conditional update.

## Cross-language test vector

The file `test-vectors/ef-pay-1.json` provides:

- the logical instruction fields;
- expected normalized amount;
- exact canonical UTF-8 JSON text;
- expected base64url SHA-256 digest without padding.

A port must reproduce the expected digest before testing signatures or settlement state. A digest mismatch is usually caused by amount scale, omitted empty fields, Unicode normalization assumptions, key ordering or base64 padding.

## Recommended production change

For multi-language interoperability, replace `EF-JCS-SUBSET-1` with full RFC 8785 JCS and publish a versioned digest projection. That is a wire-format change: do not silently change canonicalization under version `1.0`.

