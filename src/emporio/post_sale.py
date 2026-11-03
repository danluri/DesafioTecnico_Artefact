"""Offline complaint persistence and authorized return instructions."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from .order import AuthorizedPrincipal
from .order_service import OrderService


@dataclass(frozen=True, slots=True)
class Complaint:
    complaint_id: int
    order_id: int
    customer_id: int
    category: str
    description: str
    status: str
    created_at: datetime
    policy_source: str


@dataclass(frozen=True, slots=True)
class ReturnInstructions:
    order_id: int
    return_code: str
    instructions: tuple[str, ...]
    policy_source: str


class SQLiteComplaintRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS complaints (
                complaint_id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                customer_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                policy_source TEXT NOT NULL
            )
            """
        )
        self._connection.commit()

    def add(self, order_id: int, customer_id: int, category: str, description: str) -> Complaint:
        created = datetime.now(timezone.utc)
        source = "politicas_da_loja.pdf; post-sale section"
        cursor = self._connection.execute(
            "INSERT INTO complaints (order_id, customer_id, category, description, status, "
            "created_at, policy_source) VALUES (?, ?, ?, ?, 'open', ?, ?)",
            (order_id, customer_id, category, description, created.isoformat(), source),
        )
        self._connection.commit()
        return Complaint(
            cursor.lastrowid, order_id, customer_id, category, description, "open", created, source
        )

    def for_customer(
        self, order_id: int, principal: AuthorizedPrincipal
    ) -> tuple[Complaint, ...]:
        if not isinstance(principal, AuthorizedPrincipal):
            return ()
        rows = self._connection.execute(
            "SELECT * FROM complaints WHERE order_id = ? AND customer_id = ? ORDER BY complaint_id",
            (order_id, principal.customer_id),
        ).fetchall()
        return tuple(
            Complaint(
                row["complaint_id"], row["order_id"], row["customer_id"], row["category"],
                row["description"], row["status"], datetime.fromisoformat(row["created_at"]),
                row["policy_source"],
            )
            for row in rows
        )


class PostSaleService:
    def __init__(self, orders: OrderService, repository: SQLiteComplaintRepository) -> None:
        self.orders = orders
        self.repository = repository

    def create_complaint(
        self,
        order_reference: str | int | None,
        principal: AuthorizedPrincipal | None,
        *,
        category: str,
        description: str,
    ) -> Complaint | None:
        snapshot = self.orders.get_status(order_reference, principal)
        if snapshot is None or not isinstance(principal, AuthorizedPrincipal):
            return None
        if (
            not isinstance(category, str) or not category.strip()
            or not isinstance(description, str) or not description.strip()
        ):
            raise ValueError("complaint category and description are required")
        return self.repository.add(
            snapshot.order_id, principal.customer_id, category.strip(), description.strip()
        )

    complaint = create_complaint

    def request_return(
        self, order_reference: str | int | None, principal: AuthorizedPrincipal | None
    ) -> ReturnInstructions | None:
        snapshot = self.orders.get_status(order_reference, principal)
        if snapshot is None or not isinstance(principal, AuthorizedPrincipal):
            return None
        digest = hashlib.sha256(
            f"{snapshot.order_id}:{principal.customer_id}".encode()
        ).hexdigest()[:10].upper()
        return ReturnInstructions(
            snapshot.order_id,
            f"DEV-{snapshot.order_id}-{digest}",
            (
                "Embale o produto com seguran\u00e7a.",
                "Inclua o c\u00f3digo de devolu\u00e7\u00e3o na embalagem.",
                "Aguarde a an\u00e1lise da loja conforme a pol\u00edtica aplic\u00e1vel.",
            ),
            "politicas_da_loja.pdf; returns section",
        )

    return_instructions = request_return
