"""Framework-independent snapshots exposed by application presentation layers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from smart_retail.checkout.event_engine import CheckoutStateSnapshot, CheckoutUpdate
from smart_retail.domain.events import CartEvent
from smart_retail.domain.models import CartSnapshot, CheckoutSession


class ApplicationState(str, Enum):
    INITIALIZING = "initializing"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class ApplicationNotReadyError(RuntimeError):
    """Raised when a mutating presentation request has no active runtime."""


@dataclass(frozen=True, slots=True)
class CartResetResult:
    """Result of resetting shared checkout state from any presentation."""

    removed_track_count: int
    cart: CartSnapshot


@dataclass(frozen=True, slots=True)
class SessionHistory:
    """One persisted checkout session and its ordered event history."""

    session: CheckoutSession
    events: tuple[CartEvent, ...]


@dataclass(frozen=True, slots=True)
class CheckoutFrameSnapshot:
    """Consistent checkout and cart state produced from one processed frame."""

    update: CheckoutUpdate
    checkout: CheckoutStateSnapshot
    cart: CartSnapshot
