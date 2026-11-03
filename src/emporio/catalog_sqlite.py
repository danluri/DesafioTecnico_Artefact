"""Validated, atomic CSV ingestion and parameterized SQLite catalog queries."""

from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable

from .catalog import (
    CatalogIngestionError,
    CatalogNotFoundError,
    Product,
    SearchCriteria,
    SnapshotMetadata,
)

_PRODUCT_COLUMNS = {
    "product_id",
    "price_brl",
    "name",
    "category_id",
    "description",
    "stock_quantity",
    "status",
    "specs",
    "created_at",
}
_CATEGORY_COLUMNS = {"category_id", "name", "description"}
_STATUSES = {"active", "discontinued", "coming_soon"}


def _like_pattern(value: str) -> str:
    escaped = value.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _read_csv(path: Path, required: set[str]) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames
            if fieldnames is None or len(fieldnames) != len(set(fieldnames)):
                raise CatalogIngestionError(f"duplicate CSV columns in {path.name}")
            if set(fieldnames) != required:
                raise CatalogIngestionError(f"CSV columns do not match schema in {path.name}")
            rows = list(reader)
    except CatalogIngestionError:
        raise
    except (OSError, UnicodeError, csv.Error) as exc:
        raise CatalogIngestionError(f"unable to read {path.name}") from exc
    if not rows:
        raise CatalogIngestionError(f"{path.name} is empty")
    for index, row in enumerate(rows, 2):
        if set(row) != required or any(not isinstance(value, str) for value in row.values()):
            raise CatalogIngestionError(f"malformed row {index} in {path.name}")
    return rows


def _text(row: dict[str, str], key: str, *, source: str) -> str:
    value = row.get(key)
    if value is None or not value.strip():
        raise CatalogIngestionError(f"{source}: {key} is required")
    return value.strip()


def _int(row: dict[str, str], key: str, *, source: str, minimum: int = 0) -> int:
    value = _text(row, key, source=source)
    try:
        parsed = int(value)
    except ValueError as exc:
        raise CatalogIngestionError(f"{source}: {key} must be an integer") from exc
    if parsed < minimum:
        raise CatalogIngestionError(f"{source}: {key} is out of range")
    return parsed


def _money(value: str, *, source: str) -> Decimal:
    try:
        amount = Decimal(value.strip().replace(",", "."))
    except (InvalidOperation, AttributeError) as exc:
        raise CatalogIngestionError(f"{source}: price_brl is invalid") from exc
    if not amount.is_finite() or amount < 0 or amount.as_tuple().exponent < -2:
        raise CatalogIngestionError(f"{source}: price_brl is invalid")
    try:
        return amount.quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise CatalogIngestionError(f"{source}: price_brl is invalid") from exc


def _iso_datetime(value: str, *, source: str) -> str:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CatalogIngestionError(f"{source}: created_at must be ISO-8601") from exc
    return value


def _validate_rows(
    product_rows: Iterable[dict[str, str]], category_rows: Iterable[dict[str, str]] | None
) -> tuple[list[tuple[object, ...]], list[tuple[object, ...]]]:
    categories: list[tuple[object, ...]] = []
    category_ids: set[int] = set()
    if category_rows is not None:
        for index, row in enumerate(category_rows, 1):
            source = f"category row {index}"
            category_id = _int(row, "category_id", source=source)
            if category_id in category_ids:
                raise CatalogIngestionError(f"{source}: duplicate category_id")
            category_ids.add(category_id)
            categories.append(
                (category_id, _text(row, "name", source=source), row.get("description", "").strip())
            )

    products: list[tuple[object, ...]] = []
    product_ids: set[int] = set()
    for index, row in enumerate(product_rows, 1):
        source = f"product row {index}"
        product_id = _int(row, "product_id", source=source)
        if product_id in product_ids:
            raise CatalogIngestionError(f"{source}: duplicate product_id")
        product_ids.add(product_id)
        category_id = _int(row, "category_id", source=source)
        if category_rows is not None and category_id not in category_ids:
            raise CatalogIngestionError(f"{source}: unknown category_id")
        status = _text(row, "status", source=source)
        if status not in _STATUSES:
            raise CatalogIngestionError(f"{source}: unknown status")
        specs_text = _text(row, "specs", source=source)
        try:
            specs = json.loads(specs_text)
        except json.JSONDecodeError as exc:
            raise CatalogIngestionError(f"{source}: specs must be valid JSON") from exc
        if not isinstance(specs, dict):
            raise CatalogIngestionError(f"{source}: specs must be a JSON object")
        products.append(
            (
                product_id,
                    str(_money(_text(row, "price_brl", source=source), source=source)),
                _text(row, "name", source=source),
                category_id,
                row.get("description", "").strip(),
                _int(row, "stock_quantity", source=source),
                status,
                json.dumps(specs, ensure_ascii=False, sort_keys=True),
                    _iso_datetime(_text(row, "created_at", source=source), source=source),
            )
        )
    if category_rows is None:
        categories = [
            (category_id, str(category_id), "")
            for category_id in sorted({int(row[3]) for row in products})
        ]
    return products, categories


class SQLiteCatalogRepository:
    """SQLite adapter with a replace-on-success operational snapshot."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._ensure_schema()

    @classmethod
    def connect(cls, path: str | Path) -> SQLiteCatalogRepository:
        try:
            return cls(sqlite3.connect(str(path)))
        except sqlite3.Error as exc:
            raise CatalogIngestionError("unable to open catalog database") from exc

    def _ensure_schema(self) -> None:
        self._connection.executescript("""
            CREATE TABLE IF NOT EXISTS catalog_metadata (data_as_of TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS categories (
                category_id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS products (
                product_id INTEGER PRIMARY KEY,
                price_brl TEXT NOT NULL,
                name TEXT NOT NULL,
                category_id INTEGER NOT NULL REFERENCES categories(category_id),
                description TEXT NOT NULL,
                stock_quantity INTEGER NOT NULL,
                status TEXT NOT NULL,
                specs TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)
        self._connection.commit()

    def ingest(
        self,
        products_csv: Path,
        categories_csv: Path | None = None,
        *,
        data_as_of: datetime | None = None,
    ) -> SnapshotMetadata:
        try:
            metadata = SnapshotMetadata(data_as_of or datetime.now(timezone.utc))
        except (TypeError, ValueError) as exc:
            raise CatalogIngestionError("data_as_of must be timezone-aware") from exc
        products = _read_csv(products_csv, _PRODUCT_COLUMNS)
        categories = _read_csv(categories_csv, _CATEGORY_COLUMNS) if categories_csv else None
        product_values, category_values = _validate_rows(products, categories)
        try:
            with self._connection:
                self._connection.execute("DELETE FROM products")
                self._connection.execute("DELETE FROM categories")
                if category_values:
                    self._connection.executemany(
                        "INSERT INTO categories VALUES (?, ?, ?)", category_values
                    )
                self._connection.executemany(
                    "INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", product_values
                )
                self._connection.execute("DELETE FROM catalog_metadata")
                self._connection.execute(
                    "INSERT INTO catalog_metadata VALUES (?)", (metadata.data_as_of.isoformat(),)
                )
        except sqlite3.Error as exc:
            raise CatalogIngestionError("snapshot ingestion failed") from exc
        return metadata

    def _metadata(self) -> SnapshotMetadata:
        row = self._connection.execute("SELECT data_as_of FROM catalog_metadata").fetchone()
        if row is None:
            raise CatalogNotFoundError("no operational snapshot has been ingested")
        return SnapshotMetadata(datetime.fromisoformat(row[0]))

    def _product(self, row: sqlite3.Row) -> Product:
        category = self._connection.execute(
            "SELECT name FROM categories WHERE category_id = ?", (row["category_id"],)
        ).fetchone()
        return Product(
            product_id=row["product_id"],
            price_brl=Decimal(row["price_brl"]),
            name=row["name"],
            category_id=row["category_id"],
            category_name=category[0] if category else None,
            description=row["description"],
            stock_quantity=row["stock_quantity"],
            status=row["status"],
            specs=json.loads(row["specs"]),
            created_at=row["created_at"],
            snapshot=self._metadata(),
        )

    def search(self, criteria: SearchCriteria) -> tuple[tuple[Product, ...], int, SnapshotMetadata]:
        metadata = self._metadata()
        clauses: list[str] = []
        params: list[object] = []
        if criteria.availability_only:
            clauses += ["p.status = ?", "p.stock_quantity > 0"]
            params += ["active"]
        if criteria.name:
            clauses.append("LOWER(p.name) LIKE LOWER(?) ESCAPE '\\'")
            params.append(_like_pattern(criteria.name))
        if criteria.category:
            clauses.append("LOWER(c.name) LIKE LOWER(?) ESCAPE '\\'")
            params.append(_like_pattern(criteria.category))
        if criteria.maximum_budget is not None:
            clauses.append("CAST(p.price_brl AS NUMERIC) <= CAST(? AS NUMERIC)")
            params.append(str(criteria.maximum_budget))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        total_query = (
            "SELECT COUNT(*) FROM products p "
            f"LEFT JOIN categories c ON c.category_id = p.category_id{where}"
        )
        total = self._connection.execute(total_query, params).fetchone()[0]
        rows_query = (
            "SELECT p.* FROM products p "
            f"LEFT JOIN categories c ON c.category_id = p.category_id{where} "
            "ORDER BY LOWER(p.name), p.product_id LIMIT ? OFFSET ?"
        )
        rows = self._connection.execute(
            rows_query,
            [*params, criteria.limit, criteria.offset],
        ).fetchall()
        return tuple(self._product(row) for row in rows), total, metadata

    def find_by_id(self, product_id: int) -> Product | None:
        row = self._connection.execute(
            "SELECT * FROM products WHERE product_id = ?", (product_id,)
        ).fetchone()
        return self._product(row) if row else None

    def find_by_name(self, name: str) -> tuple[Product, ...]:
        rows = self._connection.execute(
            "SELECT * FROM products WHERE LOWER(name) = LOWER(?) ORDER BY product_id",
            (name.strip(),),
        ).fetchall()
        return tuple(self._product(row) for row in rows)
