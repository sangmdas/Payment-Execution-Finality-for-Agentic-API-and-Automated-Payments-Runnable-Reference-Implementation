from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .models import PaymentInstruction


class DefiniteRailFailure(Exception):
    """Rail confirms that no external effect occurred."""


class UnknownRailResult(Exception):
    """Caller cannot determine whether the external effect occurred."""


class RailAdapter(Protocol):
    def post(self, instruction: PaymentInstruction, authority_id: str) -> str: ...


@dataclass
class InMemoryRail:
    posts: list[tuple[str, PaymentInstruction]]

    def __init__(self) -> None:
        self.posts = []

    def post(self, instruction: PaymentInstruction, authority_id: str) -> str:
        settlement_ref = f"settlement-{len(self.posts) + 1}"
        self.posts.append((authority_id, instruction))
        return settlement_ref

