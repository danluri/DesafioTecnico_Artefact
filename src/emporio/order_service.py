"""Deterministic, non-enumerating order status use case."""

from __future__ import annotations

from .order import AuthorizedPrincipal, OrderStatusSnapshot
from .order_repository import OrderRepository

SAFE_ORDER_UNAVAILABLE = "Não foi possível localizar um pedido autorizado no snapshot."


class OrderService:
    def __init__(self, repository: OrderRepository) -> None:
        self._repository = repository

    def get_status(
        self, order_reference: str | int | None, principal: AuthorizedPrincipal | None
    ) -> OrderStatusSnapshot | None:
        """Return owned status, or the same safe result for every refusal path."""
        order_id = self._parse_reference(order_reference)
        if order_id is None or not isinstance(principal, AuthorizedPrincipal):
            return None
        return self._repository.find_owned_order(order_id, principal)

    status = get_status
    check_status = get_status

    @staticmethod
    def safe_message() -> str:
        return SAFE_ORDER_UNAVAILABLE

    @staticmethod
    def _parse_reference(reference: str | int | None) -> int | None:
        if isinstance(reference, bool):
            return None
        if isinstance(reference, int):
            return reference if 1 <= reference <= 2_147_483_647 else None
        if not isinstance(reference, str):
            return None
        value = reference.strip()
        if not value.isdecimal():
            return None
        try:
            parsed = int(value)
        except ValueError:
            return None
        return parsed if 1 <= parsed <= 2_147_483_647 else None
