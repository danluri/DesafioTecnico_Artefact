"""Domain types for safe, snapshot-based order status."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from .catalog import CatalogIngestionError, SnapshotMetadata


class OrderError(Exception):
    """Base error for order operations."""


class OrderIngestionError(OrderError, CatalogIngestionError):
    """Order source data is invalid and was not imported."""


class OrderReferenceError(OrderError):
    """An order reference cannot be safely interpreted."""


class OrderAuthorizationError(OrderError):
    """A request does not contain a server-established principal."""


@dataclass(frozen=True, slots=True)
class AuthorizedPrincipal:
    """Identity established by the server/session boundary, never by user text."""

    customer_id: int

    def __post_init__(self) -> None:
        if isinstance(self.customer_id, bool) or not isinstance(self.customer_id, int):
            raise ValueError("customer_id must be an integer")
        if self.customer_id < 1:
            raise ValueError("customer_id must be positive")


@dataclass(frozen=True, slots=True)
class OrderItemSummary:
    product_id: int
    quantity: int


@dataclass(frozen=True, slots=True)
class OrderStatusSnapshot:
    order_id: int
    status: str
    order_date: datetime
    total_brl: Decimal
    payment_method: str
    estimated_delivery: str | None
    items: tuple[OrderItemSummary, ...]
    snapshot: SnapshotMetadata

    @property
    def tracking_message(self) -> str:
        return (
            "A previsão de entrega está disponível no snapshot."
            if self.estimated_delivery
            else "A previsão de entrega e o rastreamento não estão disponíveis no snapshot."
        )
