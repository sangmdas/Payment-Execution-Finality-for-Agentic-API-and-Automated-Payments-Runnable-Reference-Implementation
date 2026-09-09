from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_z(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class PolicySnapshot:
    policy_epoch: int
    revocation_epoch: int
    risk_list_epoch: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class PaymentInstruction:
    act_type: str
    payer_id: str
    payer_account_ref: str
    amount: str
    currency: str
    beneficiary_id: str
    beneficiary_account_ref: str
    rail_id: str
    purpose_id: str
    sink_id: str
    mandate_id: str = ""
    invoice_ref: str = ""
    end_to_end_id: str = ""
    beneficiary_jurisdiction: str = ""
    agent_id: str = ""
    workload_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PaymentCandidateAct:
    candidate_act_id: str
    instruction: PaymentInstruction
    normalized_amount: str
    instruction_digest: str
    nonce: str
    created_at: datetime
    expires_at: datetime
    policy_state: PolicySnapshot
    canonicalization: str = "EF-JCS-SUBSET-1"
    digest_algorithm: str = "SHA-256"
    status: str = "NON_EFFECTIVE"

    def to_dict(self) -> dict[str, Any]:
        ins = self.instruction
        return {
            "version": "1.0",
            "object_type": "payment_candidate_act",
            "candidate_act_id": self.candidate_act_id,
            "act_type": ins.act_type,
            "created_at": iso_z(self.created_at),
            "expires_at": iso_z(self.expires_at),
            "payer": {
                "payer_id": ins.payer_id,
                "account_ref": ins.payer_account_ref,
                **({"agent_id": ins.agent_id} if ins.agent_id else {}),
                **({"workload_id": ins.workload_id} if ins.workload_id else {}),
            },
            "amount": self.normalized_amount,
            "currency": ins.currency.upper(),
            "beneficiary": {
                "beneficiary_id": ins.beneficiary_id,
                "account_ref": ins.beneficiary_account_ref,
                **({"jurisdiction": ins.beneficiary_jurisdiction.upper()} if ins.beneficiary_jurisdiction else {}),
            },
            "rail": {"rail_id": ins.rail_id},
            "purpose": {
                "purpose_id": ins.purpose_id,
                **({"mandate_id": ins.mandate_id} if ins.mandate_id else {}),
                **({"invoice_ref": ins.invoice_ref} if ins.invoice_ref else {}),
                **({"end_to_end_id": ins.end_to_end_id} if ins.end_to_end_id else {}),
            },
            "instruction_digest": {
                "algorithm": self.digest_algorithm,
                "value": self.instruction_digest,
                "canonicalization": self.canonicalization,
            },
            "policy_state": self.policy_state.to_dict(),
            "freshness": {"nonce": self.nonce},
            "finality_sink": {"sink_id": ins.sink_id, "sink_type": "CORE_POST"},
        }


@dataclass(frozen=True)
class ProtectedValidationEvidence:
    evidence_id: str
    candidate_act_id: str
    instruction_digest: str
    validated_predicates: dict[str, bool]
    issued_at: datetime
    key_id: str
    signature: str = ""

    def unsigned_dict(self) -> dict[str, Any]:
        return {
            "version": "1.0",
            "object_type": "protected_validation_evidence",
            "evidence_id": self.evidence_id,
            "candidate_act_id": self.candidate_act_id,
            "instruction_digest": self.instruction_digest,
            "decision": "ALLOW",
            "validated_predicates": dict(sorted(self.validated_predicates.items())),
            "issued_at": iso_z(self.issued_at),
            "protector": {"type": "HMAC-SHA-256-REFERENCE", "key_id": self.key_id},
        }

    def to_dict(self) -> dict[str, Any]:
        value = self.unsigned_dict()
        value["protector"]["signature"] = self.signature
        return value


@dataclass(frozen=True)
class PaymentFinalityAuthority:
    authority_id: str
    candidate_act_id: str
    evidence_id: str
    scope: dict[str, str]
    binding: dict[str, Any]
    issued_at: datetime
    expires_at: datetime
    key_id: str
    single_use: bool = True
    signature: str = ""

    def unsigned_dict(self) -> dict[str, Any]:
        return {
            "version": "1.0",
            "object_type": "payment_finality_authority",
            "authority_id": self.authority_id,
            "candidate_act_id": self.candidate_act_id,
            "evidence_id": self.evidence_id,
            "scope": self.scope,
            "binding": self.binding,
            "lifetime": {
                "issued_at": iso_z(self.issued_at),
                "expires_at": iso_z(self.expires_at),
                "single_use": self.single_use,
            },
            "protector": {"type": "HMAC-SHA-256-REFERENCE", "key_id": self.key_id},
        }

    def to_dict(self) -> dict[str, Any]:
        value = self.unsigned_dict()
        value["protector"]["signature"] = self.signature
        return value
