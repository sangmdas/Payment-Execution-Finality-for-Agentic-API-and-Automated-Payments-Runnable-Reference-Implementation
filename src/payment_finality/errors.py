from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Decision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    ESCALATE = "ESCALATE"


class Code(str, Enum):
    NO_FINALITY_AUTHORITY = "EF-002"
    AUTHORITY_ALREADY_USED = "EF-005"
    REPLAY_DETECTED = "EF-006"
    MALFORMED_ACT = "EF-010"
    INVALID_AUTHORITY = "EF-011"
    EXPIRED_AUTHORITY = "EF-012"
    EVIDENCE_MISSING = "EF-013"
    INSTRUCTION_SUBSTITUTION = "EF-023"
    AMOUNT_MISMATCH = "EF-024"
    BENEFICIARY_MISMATCH = "EF-025"
    RAIL_MISMATCH = "EF-026"
    MANDATE_MISS = "EF-027"
    PAYEE_BLOCKED = "EF-028"
    AMOUNT_ENVELOPE = "EF-029"
    CURRENCY_MISMATCH = "EF-030"
    PURPOSE_MISMATCH = "EF-031"
    EPOCH_MISMATCH = "EF-032"
    SINK_MISMATCH = "EF-040"
    HOLDER_MISMATCH = "EF-041"
    ESCALATION_REQUIRED = "EF-070"
    FAIL_CLOSED = "EF-080"
    RAIL_RESULT_UNKNOWN = "EF-090"


@dataclass
class FinalityError(Exception):
    code: Code
    message: str
    retryable: bool = False

    def __str__(self) -> str:
        return f"{self.code.value} {self.message}"
