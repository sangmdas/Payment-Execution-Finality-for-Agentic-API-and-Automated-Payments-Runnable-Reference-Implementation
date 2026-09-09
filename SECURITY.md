# Security policy and integration requirements

## Threat model demonstrated

The tests exercise denial of amount, currency, beneficiary, beneficiary-account, rail, purpose, mandate, invoice, sink, agent and workload substitution; stale epochs; expired/tampered authority; replay; concurrent consume; and ambiguous rail failure.

## Critical production requirements

- Keep authority-signing keys off agent and model hosts.
- Make the sink the only route to the effecting rail function and its credential.
- Use protected, append-aware evidence storage and strongly consistent consume state.
- Bind every economic, identity, purpose, jurisdiction and routing field that can change the consequence.
- Verify evidence and authority independently at the sink.
- Treat missing/invalid state and timeouts as deny or hold.
- Never automatically reissue or retry while a prior authority is `CONSUMED_PENDING`.
- Redact/tokenize account data in logs; correlate `authority_id`, digest, consume time and settlement reference.
- Separate cold-path approval from hot-path cached evaluation, while retaining digest and consume checks on both.
- Monitor alternate posting paths continuously.

## Reporting vulnerabilities

Do not include live payment credentials, personal data or exploitable production details in a public issue. Use the repository owner's private security-reporting channel when configured.

