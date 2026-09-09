from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import secrets
from typing import Callable

from .canonical import digest_instruction, normalize_amount
from .crypto import Authenticator
from .errors import Code, FinalityError
from .models import (
    PaymentCandidateAct, PaymentFinalityAuthority, PaymentInstruction,
    ProtectedValidationEvidence, utc_now,
)
from .policy import InMemoryPolicy
from .store import SQLiteFinalityStore


class ProtectedEnforcementDomain:
    def __init__(self, policy: InMemoryPolicy, store: SQLiteFinalityStore,
                 authenticator: Authenticator, ttl_seconds: float = 10.0,
                 clock: Callable = utc_now) -> None:
        self.policy = policy
        self.store = store
        self.authenticator = authenticator
        self.ttl_seconds = ttl_seconds
        self.clock = clock

    def prepare(self, instruction: PaymentInstruction) -> PaymentCandidateAct:
        now = self.clock()
        normalized = normalize_amount(instruction.amount, instruction.currency)
        return PaymentCandidateAct(
            candidate_act_id="act-" + secrets.token_urlsafe(18),
            instruction=instruction,
            normalized_amount=normalized,
            instruction_digest=digest_instruction(instruction, normalized),
            nonce=secrets.token_urlsafe(24),
            created_at=now,
            expires_at=now + timedelta(seconds=self.ttl_seconds),
            policy_state=self.policy.snapshot,
        )

    def validate_and_issue(self, act: PaymentCandidateAct) -> tuple[ProtectedValidationEvidence, PaymentFinalityAuthority]:
        now = self.clock()
        if act.status != "NON_EFFECTIVE" or now >= act.expires_at:
            raise FinalityError(Code.EXPIRED_AUTHORITY, "candidate is stale or not non-effective")
        predicates = self.policy.validate(act)
        evidence = ProtectedValidationEvidence(
            evidence_id="pve-" + secrets.token_urlsafe(18),
            candidate_act_id=act.candidate_act_id,
            instruction_digest=act.instruction_digest,
            validated_predicates=predicates,
            issued_at=now,
            key_id=self.authenticator.key_id,
        )
        evidence = replace(evidence, signature=self.authenticator.sign(evidence.unsigned_dict()))
        self.store.commit_evidence(evidence)

        ins = act.instruction
        binding = {
            "instruction_digest": {"algorithm": act.digest_algorithm, "value": act.instruction_digest},
            "nonce": act.nonce,
            "policy_epoch": act.policy_state.policy_epoch,
            "revocation_epoch": act.policy_state.revocation_epoch,
            "risk_list_epoch": act.policy_state.risk_list_epoch,
            "finality_sink_id": ins.sink_id,
            "holder": {"agent_id": ins.agent_id, "workload_id": ins.workload_id},
        }
        authority = PaymentFinalityAuthority(
            authority_id="pfa-" + secrets.token_urlsafe(18),
            candidate_act_id=act.candidate_act_id,
            evidence_id=evidence.evidence_id,
            scope={
                "act_type": ins.act_type, "amount": act.normalized_amount,
                "currency": ins.currency.upper(), "beneficiary_id": ins.beneficiary_id,
                "beneficiary_account_ref": ins.beneficiary_account_ref,
                "rail_id": ins.rail_id, "purpose_id": ins.purpose_id,
            },
            binding=binding,
            issued_at=now,
            expires_at=act.expires_at,
            key_id=self.authenticator.key_id,
        )
        authority = replace(authority, signature=self.authenticator.sign(authority.unsigned_dict()))
        self.store.register_authority(authority)
        return evidence, authority

