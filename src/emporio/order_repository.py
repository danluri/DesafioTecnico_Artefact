"""Typed read-only port for authorized order snapshots."""

from __future__ import annotations

from typing import Protocol

from .catalog import SnapshotMetadata
from .order import AuthorizedPrincipal, OrderStatusSnapshot


class OrderRepository(Protocol):
    def find_owned_order(
        self, order_id: int, principal: AuthorizedPrincipal
    ) -> OrderStatusSnapshot | None:
        """Return an order only when its customer matches the server principal."""

    def order_snapshot_metadata(self) -> SnapshotMetadata:
        """Return the operational snapshot provenance."""

    def find_owned_tracking_code(
        self, order_id: int, principal: AuthorizedPrincipal
    ) -> str | None:
        """Return a tracking code only after ownership succeeds."""
