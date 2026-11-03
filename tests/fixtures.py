"""Synthetic, deterministic fixtures shared by offline verification tests."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

PRODUCT_FIELDS = [
    "product_id", "price_brl", "name", "category_id", "description",
    "stock_quantity", "status", "specs", "created_at",
]
CUSTOMER_FIELDS = ["customer_id", "name", "phone", "email", "city"]
ORDER_FIELDS = [
    "order_id", "customer_id", "order_date", "status", "total_brl",
    "payment_method", "tracking_code", "estimated_delivery", "notes",
]
ITEM_FIELDS = ["order_id", "quantity", "product_id"]


def write_csv(path: Path, fields: list[str], rows: Iterable[dict[str, str]]) -> Path:
    """Write only synthetic rows and return the created path."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def product(
    product_id: str, name: str = "Instrumento Sintético", price: str = "100.00"
) -> dict[str, str]:
    return {
        "product_id": product_id,
        "price_brl": price,
        "name": name,
        "category_id": "1",
        "description": "Fixture determinística sem dados reais",
        "stock_quantity": "3",
        "status": "active",
        "specs": '{"color": "natural"}',
        "created_at": "2026-01-01T00:00:00Z",
    }


def snapshot_files(root: Path) -> dict[str, Path]:
    """Create a complete anonymized catalog/order snapshot under ``root``."""
    paths = {name: root / f"{name}.csv" for name in ("products", "customers", "orders", "items")}
    write_csv(paths["products"], PRODUCT_FIELDS, [product("7")])
    write_csv(paths["customers"], CUSTOMER_FIELDS, [
        {"customer_id": "3", "name": "Cliente Sintético A", "phone": "00000000000",
         "email": "cliente-a@example.invalid", "city": "Cidade A"},
        {"customer_id": "8", "name": "Cliente Sintético B", "phone": "11111111111",
         "email": "cliente-b@example.invalid", "city": "Cidade B"},
    ])
    write_csv(paths["orders"], ORDER_FIELDS, [
        {"order_id": "1", "customer_id": "3", "order_date": "2026-11-02T12:00:00Z",
         "status": "shipped", "total_brl": "100.00", "payment_method": "pix",
         "tracking_code": "SYNTHETIC-TRACKING", "estimated_delivery": "2026-11-08",
         "notes": "synthetic note"},
        {"order_id": "2", "customer_id": "8", "order_date": "2026-11-02T13:00:00Z",
         "status": "pending", "total_brl": "100.00", "payment_method": "card",
         "tracking_code": "", "estimated_delivery": "", "notes": ""},
    ])
    write_csv(paths["items"], ITEM_FIELDS, [
        {"order_id": "1", "quantity": "1", "product_id": "7"},
        {"order_id": "2", "quantity": "1", "product_id": "7"},
    ])
    return paths


def snapshot_timestamp() -> datetime:
    return datetime(2026, 11, 3, tzinfo=timezone.utc)
