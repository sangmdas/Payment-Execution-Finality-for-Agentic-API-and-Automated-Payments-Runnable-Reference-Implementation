"""Reference implementation for payment execution finality."""

from .crypto import HMACAuthenticator
from .errors import Decision, FinalityError
from .models import PaymentInstruction, PolicySnapshot
from .ped import ProtectedEnforcementDomain
from .policy import InMemoryPolicy
from .rail import InMemoryRail
from .sink import SettlementSink
from .store import SQLiteFinalityStore

__all__ = [
    "Decision",
    "FinalityError",
    "HMACAuthenticator",
    "InMemoryPolicy",
    "InMemoryRail",
    "PaymentInstruction",
    "PolicySnapshot",
    "ProtectedEnforcementDomain",
    "SQLiteFinalityStore",
    "SettlementSink",
]

