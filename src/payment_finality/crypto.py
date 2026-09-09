from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Any, Protocol

from .canonical import canonical_json


class Authenticator(Protocol):
    key_id: str

    def sign(self, value: dict[str, Any]) -> str: ...
    def verify(self, value: dict[str, Any], signature: str) -> bool: ...


class HMACAuthenticator:
    """Portable test authenticator. Replace with HSM/KMS signatures in production."""

    def __init__(self, key: bytes, key_id: str = "reference-hmac-key") -> None:
        if len(key) < 32:
            raise ValueError("reference HMAC key must be at least 32 bytes")
        self._key = key
        self.key_id = key_id

    def sign(self, value: dict[str, Any]) -> str:
        mac = hmac.new(self._key, canonical_json(value), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(mac).rstrip(b"=").decode("ascii")

    def verify(self, value: dict[str, Any], signature: str) -> bool:
        return hmac.compare_digest(self.sign(value), signature)

