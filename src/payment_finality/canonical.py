from __future__ import annotations

import base64
import hashlib
import json
from decimal import Decimal, InvalidOperation
from typing import Any

from .errors import Code, FinalityError
from .models import PaymentInstruction


CURRENCY_SCALE = {
    "BHD": 3, "CLP": 0, "EUR": 2, "GBP": 2, "INR": 2,
    "JPY": 0, "KWD": 3, "OMR": 3, "USD": 2,
}


def canonical_json(value: Any) -> bytes:
    """Stable UTF-8 JSON subset; see docs/LIMITATIONS.md regarding full RFC 8785."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def normalize_amount(amount: str, currency: str, scale_map: dict[str, int] | None = None) -> str:
    scales = scale_map or CURRENCY_SCALE
    if not isinstance(amount, str) or amount.startswith(("+", "-")):
        raise FinalityError(Code.MALFORMED_ACT, "amount must be an unsigned decimal string")
    try:
        decimal = Decimal(amount)
    except (InvalidOperation, ValueError) as exc:
        raise FinalityError(Code.MALFORMED_ACT, "invalid decimal amount") from exc
    if not decimal.is_finite() or decimal <= 0:
        raise FinalityError(Code.MALFORMED_ACT, "amount must be finite and greater than zero")
    scale = scales.get(currency.upper(), 2)
    quantum = Decimal(1).scaleb(-scale)
    normalized = decimal.quantize(quantum)
    if normalized != decimal:
        raise FinalityError(Code.MALFORMED_ACT, f"amount exceeds configured {currency.upper()} scale {scale}")
    return f"{normalized:.{scale}f}"


def instruction_projection(instruction: PaymentInstruction, normalized_amount: str) -> dict[str, Any]:
    """All fields below are load-bearing in profile EF-PAY-1."""
    return {
        "act_type": instruction.act_type,
        "payer": {
            "payer_id": instruction.payer_id,
            "account_ref": instruction.payer_account_ref,
            "agent_id": instruction.agent_id,
            "workload_id": instruction.workload_id,
        },
        "amount": normalized_amount,
        "currency": instruction.currency.upper(),
        "beneficiary": {
            "beneficiary_id": instruction.beneficiary_id,
            "account_ref": instruction.beneficiary_account_ref,
            "jurisdiction": instruction.beneficiary_jurisdiction.upper(),
        },
        "rail": {"rail_id": instruction.rail_id},
        "purpose": {
            "purpose_id": instruction.purpose_id,
            "mandate_id": instruction.mandate_id,
            "invoice_ref": instruction.invoice_ref,
            "end_to_end_id": instruction.end_to_end_id,
        },
    }


def digest_instruction(instruction: PaymentInstruction, normalized_amount: str | None = None) -> str:
    normalized = normalized_amount or normalize_amount(instruction.amount, instruction.currency)
    digest = hashlib.sha256(canonical_json(instruction_projection(instruction, normalized))).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
