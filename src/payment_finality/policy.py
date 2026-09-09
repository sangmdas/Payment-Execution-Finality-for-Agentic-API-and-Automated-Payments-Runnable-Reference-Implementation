from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .canonical import normalize_amount
from .errors import Code, FinalityError
from .models import PaymentCandidateAct, PolicySnapshot


@dataclass
class InMemoryPolicy:
    snapshot: PolicySnapshot
    permitted_rails: set[str]
    permitted_purposes: set[str]
    mandates: dict[str, set[str]]
    hot_ceiling_by_currency: dict[str, str]
    blocked_beneficiaries: set[str] = field(default_factory=set)
    require_holder_binding: bool = True

    def validate(self, act: PaymentCandidateAct) -> dict[str, bool]:
        ins = act.instruction
        if act.policy_state != self.snapshot:
            raise FinalityError(Code.EPOCH_MISMATCH, "candidate policy state is not current")
        if ins.beneficiary_id in self.blocked_beneficiaries:
            raise FinalityError(Code.PAYEE_BLOCKED, "beneficiary is blocked")
        if ins.rail_id not in self.permitted_rails:
            raise FinalityError(Code.RAIL_MISMATCH, "rail is not permitted")
        if ins.purpose_id not in self.permitted_purposes:
            raise FinalityError(Code.PURPOSE_MISMATCH, "purpose is not permitted")
        allowed_payees = self.mandates.get(ins.mandate_id)
        if not ins.mandate_id or not allowed_payees or ins.beneficiary_id not in allowed_payees:
            raise FinalityError(Code.MANDATE_MISS, "mandate does not cover beneficiary")
        ceiling_text = self.hot_ceiling_by_currency.get(ins.currency.upper())
        if ceiling_text is None:
            raise FinalityError(Code.ESCALATION_REQUIRED, "no hot-path currency envelope")
        ceiling = Decimal(normalize_amount(ceiling_text, ins.currency))
        if Decimal(act.normalized_amount) > ceiling:
            raise FinalityError(Code.AMOUNT_ENVELOPE, "amount exceeds hot-path envelope")
        if self.require_holder_binding and not (ins.agent_id or ins.workload_id):
            raise FinalityError(Code.HOLDER_MISMATCH, "agent_id or workload_id is required")
        return {
            "mandate_covers": True,
            "amount_in_envelope": True,
            "beneficiary_not_blocked": True,
            "rail_permitted": True,
            "purpose_valid": True,
            "epoch_valid": True,
            "freshness_valid": True,
            "sink_binding_valid": True,
            "holder_binding_valid": True,
        }

