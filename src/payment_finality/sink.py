from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from .canonical import digest_instruction, normalize_amount
from .crypto import Authenticator
from .errors import Code, FinalityError
from .models import PaymentFinalityAuthority, PaymentInstruction, PolicySnapshot
from .rail import DefiniteRailFailure, RailAdapter, UnknownRailResult
from .store import SQLiteFinalityStore


class SettlementSink:
    def __init__(self, sink_id: str, store: SQLiteFinalityStore,
                 authenticator: Authenticator, rail: RailAdapter,
                 current_policy: Callable[[], PolicySnapshot]) -> None:
        self.sink_id = sink_id
        self.store = store
        self.authenticator = authenticator
        self.rail = rail
        self.current_policy = current_policy

    def verify_and_post(self, live: PaymentInstruction,
                        authority: PaymentFinalityAuthority,
                        now: datetime | None = None) -> str:
        now = now or datetime.now(timezone.utc)
        if not self.authenticator.verify(authority.unsigned_dict(), authority.signature):
            raise FinalityError(Code.INVALID_AUTHORITY, "authority integrity check failed")
        evidence = self.store.evidence_payload(authority.evidence_id)
        if evidence is None:
            raise FinalityError(Code.EVIDENCE_MISSING, "protected validation evidence cannot be resolved")
        evidence_signature = evidence["protector"].pop("signature")
        if not self.authenticator.verify(evidence, evidence_signature):
            raise FinalityError(Code.INVALID_AUTHORITY, "evidence integrity check failed")
        if (evidence.get("decision") != "ALLOW" or
                evidence.get("candidate_act_id") != authority.candidate_act_id or
                evidence.get("protector", {}).get("key_id") != self.authenticator.key_id or
                not evidence.get("validated_predicates") or
                not all(evidence["validated_predicates"].values())):
            raise FinalityError(Code.INVALID_AUTHORITY, "evidence claims are not valid for this authority")
        if evidence["instruction_digest"] != authority.binding["instruction_digest"]["value"]:
            raise FinalityError(Code.INVALID_AUTHORITY, "evidence and authority digest differ")
        if now >= authority.expires_at:
            raise FinalityError(Code.EXPIRED_AUTHORITY, "authority expired")
        if authority.binding["finality_sink_id"] != self.sink_id or live.sink_id != self.sink_id:
            raise FinalityError(Code.SINK_MISMATCH, "authority or live instruction targets another sink")

        current = self.current_policy()
        for field in ("policy_epoch", "revocation_epoch", "risk_list_epoch"):
            if authority.binding[field] != getattr(current, field):
                raise FinalityError(Code.EPOCH_MISMATCH, f"{field} is stale")

        normalized = normalize_amount(live.amount, live.currency)
        digest = digest_instruction(live, normalized)
        if digest != authority.binding["instruction_digest"]["value"]:
            raise FinalityError(Code.INSTRUCTION_SUBSTITUTION, "live instruction digest does not match authority")
        scope = authority.scope
        checks = (
            (normalized == scope["amount"], Code.AMOUNT_MISMATCH, "amount mismatch"),
            (live.currency.upper() == scope["currency"], Code.CURRENCY_MISMATCH, "currency mismatch"),
            (live.beneficiary_id == scope["beneficiary_id"] and live.beneficiary_account_ref == scope["beneficiary_account_ref"], Code.BENEFICIARY_MISMATCH, "beneficiary mismatch"),
            (live.rail_id == scope["rail_id"], Code.RAIL_MISMATCH, "rail mismatch"),
            (live.purpose_id == scope["purpose_id"], Code.PURPOSE_MISMATCH, "purpose mismatch"),
        )
        for passed, code, message in checks:
            if not passed:
                raise FinalityError(code, message)
        holder = authority.binding["holder"]
        if live.agent_id != holder["agent_id"] or live.workload_id != holder["workload_id"]:
            raise FinalityError(Code.HOLDER_MISMATCH, "authority is not bound to this agent/workload")

        self.store.reserve(authority.authority_id, digest, self.sink_id)
        try:
            settlement_ref = self.rail.post(live, authority.authority_id)
        except DefiniteRailFailure:
            self.store.fail_definite(authority.authority_id)
            raise
        except UnknownRailResult as exc:
            # Keep CONSUMED_PENDING. Never retry the value movement blindly.
            raise FinalityError(Code.RAIL_RESULT_UNKNOWN, "reconcile before any retry", retryable=False) from exc
        except Exception as exc:
            # An unclassified exception is uncertain, so fail closed and retain the consume reservation.
            raise FinalityError(Code.RAIL_RESULT_UNKNOWN, "unclassified rail failure; reconcile", retryable=False) from exc
        self.store.complete(authority.authority_id, settlement_ref)
        return settlement_ref
