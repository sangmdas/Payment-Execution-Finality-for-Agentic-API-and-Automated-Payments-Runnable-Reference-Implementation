from __future__ import annotations

import json

from .crypto import HMACAuthenticator
from .models import PaymentInstruction, PolicySnapshot
from .ped import ProtectedEnforcementDomain
from .policy import InMemoryPolicy
from .rail import InMemoryRail
from .sink import SettlementSink
from .store import SQLiteFinalityStore


def build_demo():
    snapshot = PolicySnapshot(12, 4, 7)
    policy = InMemoryPolicy(
        snapshot=snapshot,
        permitted_rails={"SEPA_INSTANT"},
        permitted_purposes={"invoice-pay"},
        mandates={"mandate-vendors": {"vendor-441"}},
        hot_ceiling_by_currency={"EUR": "500.00"},
    )
    store = SQLiteFinalityStore()
    auth = HMACAuthenticator(b"reference-key-material-32-bytes!!")
    rail = InMemoryRail()
    ped = ProtectedEnforcementDomain(policy, store, auth)
    sink = SettlementSink("core-post-eu-1", store, auth, rail, lambda: policy.snapshot)
    return policy, store, ped, sink, rail


def sample_instruction() -> PaymentInstruction:
    return PaymentInstruction(
        act_type="INSTANT_CREDIT", payer_id="enterprise-7", payer_account_ref="acct-payer-1",
        amount="150", currency="EUR", beneficiary_id="vendor-441",
        beneficiary_account_ref="acct-vendor-441", rail_id="SEPA_INSTANT",
        purpose_id="invoice-pay", sink_id="core-post-eu-1",
        mandate_id="mandate-vendors", invoice_ref="INV-2026-441",
        agent_id="ap-agent-1", workload_id="spiffe://example/ap-agent/1",
    )


def main() -> None:
    _, store, ped, sink, rail = build_demo()
    instruction = sample_instruction()
    act = ped.prepare(instruction)
    evidence, authority = ped.validate_and_issue(act)
    settlement_ref = sink.verify_and_post(instruction, authority)
    print(json.dumps({
        "candidate_status": act.status,
        "instruction_digest": act.instruction_digest,
        "evidence_id": evidence.evidence_id,
        "authority_id": authority.authority_id,
        "authority_state": store.state(authority.authority_id),
        "settlement_ref": settlement_ref,
        "rail_post_count": len(rail.posts),
    }, indent=2))


if __name__ == "__main__":
    main()

