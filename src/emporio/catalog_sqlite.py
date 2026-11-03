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
    Promotion,
    SearchCriteria,
    SnapshotMetadata,
)
from .order import AuthorizedPrincipal, OrderIngestionError, OrderItemSummary, OrderStatusSnapshot

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
_PROMOTION_COLUMNS = {"promotion_id", "product_id", "discount_percent", "description", "is_active"}
_CUSTOMER_COLUMNS = {"customer_id", "name", "phone", "email", "city"}
_ORDER_COLUMNS = {
    "order_id", "customer_id", "order_date", "status", "total_brl", "payment_method",
    "tracking_code", "estimated_delivery", "notes",
}
_ORDER_ITEM_COLUMNS = {"order_id", "quantity", "product_id"}
_ORDER_STATUSES = {"pending", "confirmed", "shipped", "delivered", "cancelled"}
_PAYMENT_METHODS = {"pix", "card", "cash", *{f"credit_{count}x" for count in range(1, 13)}}


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


def _percent(value: str, *, source: str) -> Decimal:
    try:
        amount = Decimal(value.strip().replace(",", "."))
    except (InvalidOperation, AttributeError) as exc:
        raise CatalogIngestionError(f"{source}: discount_percent is invalid") from exc
    if not amount.is_finite() or amount < 0 or amount > 100 or amount.as_tuple().exponent < -2:
        raise CatalogIngestionError(f"{source}: discount_percent is invalid")
    return amount.quantize(Decimal("0.01"))


def _bool_flag(value: str, *, source: str) -> int:
    if value.strip() not in {"0", "1"}:
        raise CatalogIngestionError(f"{source}: is_active must be 0 or 1")
    return int(value.strip())


def _iso_datetime(value: str, *, source: str) -> str:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CatalogIngestionError(f"{source}: created_at must be ISO-8601") from exc
    return value


def _order_datetime(value: str, *, source: str) -> str:
    value = _text({"value": value}, "value", source=source)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OrderIngestionError(f"{source}: order_date must be ISO-8601") from exc
    if parsed.tzinfo is None:
        if len(value) == 10:
            return datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc).isoformat()
        raise OrderIngestionError(f"{source}: order_date must include a timezone")
    return parsed.isoformat()


def _validate_order_rows(
    customer_rows: Iterable[dict[str, str]],
    order_rows: Iterable[dict[str, str]],
    item_rows: Iterable[dict[str, str]],
    known_product_ids: set[int] | None = None,
) -> tuple[list[tuple[object, ...]], list[tuple[object, ...]], list[tuple[object, ...]]]:
    customers: list[tuple[object, ...]] = []
    customer_ids: set[int] = set()
    for index, row in enumerate(customer_rows, 1):
        source = f"customer row {index}"
        customer_id = _int(row, "customer_id", source=source, minimum=1)
        if customer_id in customer_ids:
            raise OrderIngestionError(f"{source}: duplicate customer_id")
        customer_ids.add(customer_id)
        customers.append(
            (customer_id, _text(row, "name", source=source),
             _text(row, "phone", source=source), _text(row, "email", source=source),
             _text(row, "city", source=source))
        )

    orders: list[tuple[object, ...]] = []
    order_ids: set[int] = set()
    for index, row in enumerate(order_rows, 1):
        source = f"order row {index}"
        order_id = _int(row, "order_id", source=source, minimum=1)
        if order_id in order_ids:
            raise OrderIngestionError(f"{source}: duplicate order_id")
        order_ids.add(order_id)
        customer_id = _int(row, "customer_id", source=source, minimum=1)
        if customer_id not in customer_ids:
            raise OrderIngestionError(f"{source}: unknown customer_id")
        status = _text(row, "status", source=source)
        if status not in _ORDER_STATUSES:
            raise OrderIngestionError(f"{source}: unknown status")
        order_date = _order_datetime(_text(row, "order_date", source=source), source=source)
        total = _money(_text(row, "total_brl", source=source), source=source)
        payment_method = _text(row, "payment_method", source=source)
        if payment_method not in _PAYMENT_METHODS:
            raise OrderIngestionError(f"{source}: unknown payment_method")
        orders.append(
            (order_id, customer_id, order_date, status, str(total), payment_method,
             row.get("tracking_code", "").strip(),
             row.get("estimated_delivery", "").strip(), row.get("notes", "").strip())
        )

    items: list[tuple[object, ...]] = []
    item_keys: set[tuple[int, int]] = set()
    for index, row in enumerate(item_rows, 1):
        source = f"order item row {index}"
        order_id = _int(row, "order_id", source=source, minimum=1)
        product_id = _int(row, "product_id", source=source, minimum=1)
        quantity = _int(row, "quantity", source=source, minimum=1)
        key = (order_id, product_id)
        if (
            order_id not in order_ids
            or key in item_keys
            or (known_product_ids is not None and product_id not in known_product_ids)
        ):
            raise OrderIngestionError(f"{source}: invalid or duplicate item")
        item_keys.add(key)
        items.append((order_id, product_id, quantity))
    if order_ids and not items:
        raise OrderIngestionError("orders must have order items")
    if {item[0] for item in items} != order_ids:
        raise OrderIngestionError("every order must have items")
    return customers, orders, items


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


def _validate_promotions(
    rows: Iterable[dict[str, str]], product_ids: set[int]
) -> list[tuple[object, ...]]:
    values: list[tuple[object, ...]] = []
    seen: set[int] = set()
    for index, row in enumerate(rows, 1):
        source = f"promotion row {index}"
        promotion_id = _int(row, "promotion_id", source=source)
        if promotion_id in seen:
            raise CatalogIngestionError(f"{source}: duplicate promotion_id")
        seen.add(promotion_id)
        product_id = _int(row, "product_id", source=source)
        if product_id not in product_ids:
            raise CatalogIngestionError(f"{source}: unknown product_id")
        discount = _percent(_text(row, "discount_percent", source=source), source=source)
        description = _text(row, "description", source=source)
        active = _bool_flag(_text(row, "is_active", source=source), source=source)
        values.append((promotion_id, product_id, str(discount), description, active))
    return values


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
            CREATE TABLE IF NOT EXISTS order_metadata (data_as_of TEXT NOT NULL);
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
            CREATE TABLE IF NOT EXISTS promotions (
                promotion_id INTEGER PRIMARY KEY,
                product_id INTEGER NOT NULL REFERENCES products(product_id),
                discount_percent TEXT NOT NULL,
                description TEXT NOT NULL,
                is_active INTEGER NOT NULL CHECK (is_active IN (0, 1))
            );
            CREATE TABLE IF NOT EXISTS customers (
                customer_id INTEGER PRIMARY KEY, name TEXT NOT NULL, phone TEXT NOT NULL,
                email TEXT NOT NULL, city TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS orders (
                order_id INTEGER PRIMARY KEY,
                customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
                order_date TEXT NOT NULL, status TEXT NOT NULL, total_brl TEXT NOT NULL,
                payment_method TEXT NOT NULL, tracking_code TEXT NOT NULL,
                estimated_delivery TEXT NOT NULL, notes TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS order_items (
                order_id INTEGER NOT NULL REFERENCES orders(order_id),
                product_id INTEGER NOT NULL, quantity INTEGER NOT NULL,
                PRIMARY KEY (order_id, product_id)
            );
        """)
        self._connection.commit()

    def ingest(
        self,
        products_csv: Path,
        categories_csv: Path | None = None,
        promotions_csv: Path | None = None,
        *,
        data_as_of: datetime | None = None,
        customers_csv: Path | None = None,
        orders_csv: Path | None = None,
        order_items_csv: Path | None = None,
    ) -> SnapshotMetadata:
        try:
            metadata = SnapshotMetadata(data_as_of or datetime.now(timezone.utc))
        except (TypeError, ValueError) as exc:
            raise CatalogIngestionError("data_as_of must be timezone-aware") from exc
        products = _read_csv(products_csv, _PRODUCT_COLUMNS)
        categories = _read_csv(categories_csv, _CATEGORY_COLUMNS) if categories_csv else None
        product_values, category_values = _validate_rows(products, categories)
        promotion_values = _validate_promotions(
            _read_csv(promotions_csv, _PROMOTION_COLUMNS),
            {int(value[0]) for value in product_values},
        ) if promotions_csv else []
        order_sources = (customers_csv, orders_csv, order_items_csv)
        if any(order_sources) and not all(order_sources):
            raise OrderIngestionError("customer, order, and item sources are required together")
        customer_values: list[tuple[object, ...]] = []
        order_values: list[tuple[object, ...]] = []
        item_values: list[tuple[object, ...]] = []
        if all(order_sources):
            customer_values, order_values, item_values = _validate_order_rows(
                _read_csv(customers_csv, _CUSTOMER_COLUMNS),
                _read_csv(orders_csv, _ORDER_COLUMNS),
                _read_csv(order_items_csv, _ORDER_ITEM_COLUMNS),
                {int(value[0]) for value in product_values},
            )
        elif self._connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0]:
            raise OrderIngestionError(
                "catalog and order sources must be refreshed together once orders exist"
            )
        try:
            with self._connection:
                if customer_values:
                    self._connection.execute("DELETE FROM order_items")
                    self._connection.execute("DELETE FROM orders")
                    self._connection.execute("DELETE FROM customers")
                self._connection.execute("DELETE FROM promotions")
                self._connection.execute("DELETE FROM products")
                self._connection.execute("DELETE FROM categories")
                if category_values:
                    self._connection.executemany(
                        "INSERT INTO categories VALUES (?, ?, ?)", category_values
                    )
                self._connection.executemany(
                    "INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", product_values
                )
                if promotion_values:
                    self._connection.executemany(
                        "INSERT INTO promotions VALUES (?, ?, ?, ?, ?)", promotion_values
                    )
                if customer_values:
                    self._connection.executemany(
                        "INSERT INTO customers VALUES (?, ?, ?, ?, ?)", customer_values
                    )
                    self._connection.executemany(
                        "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", order_values
                    )
                    self._connection.executemany(
                        "INSERT INTO order_items VALUES (?, ?, ?)", item_values
                    )
                self._connection.execute("DELETE FROM catalog_metadata")
                self._connection.execute(
                    "INSERT INTO catalog_metadata VALUES (?)", (metadata.data_as_of.isoformat(),)
                )
                if customer_values:
                    self._connection.execute("DELETE FROM order_metadata")
                    self._connection.execute(
                        "INSERT INTO order_metadata VALUES (?)", (metadata.data_as_of.isoformat(),)
                    )
        except sqlite3.Error as exc:
            raise CatalogIngestionError("snapshot ingestion failed") from exc
        return metadata

    def ingest_orders(
        self,
        customers_csv: Path,
        orders_csv: Path,
        order_items_csv: Path,
        *,
        data_as_of: datetime | None = None,
    ) -> SnapshotMetadata:
        """Atomically replace only the order snapshot, for an existing database."""
        try:
            metadata = SnapshotMetadata(data_as_of or datetime.now(timezone.utc))
        except (TypeError, ValueError) as exc:
            raise OrderIngestionError("data_as_of must be timezone-aware") from exc
        customer_values, order_values, item_values = _validate_order_rows(
            _read_csv(customers_csv, _CUSTOMER_COLUMNS),
            _read_csv(orders_csv, _ORDER_COLUMNS),
            _read_csv(order_items_csv, _ORDER_ITEM_COLUMNS),
            {row[0] for row in self._connection.execute("SELECT product_id FROM products")},
        )
        try:
            with self._connection:
                self._connection.execute("DELETE FROM order_items")
                self._connection.execute("DELETE FROM orders")
                self._connection.execute("DELETE FROM customers")
                self._connection.executemany(
                    "INSERT INTO customers VALUES (?, ?, ?, ?, ?)", customer_values
                )
                self._connection.executemany(
                    "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", order_values
                )
                self._connection.executemany(
                    "INSERT INTO order_items VALUES (?, ?, ?)", item_values
                )
                self._connection.execute("DELETE FROM order_metadata")
                self._connection.execute(
                    "INSERT INTO order_metadata VALUES (?)", (metadata.data_as_of.isoformat(),)
                )
        except sqlite3.Error as exc:
            raise OrderIngestionError("order snapshot ingestion failed") from exc
        return metadata

    def order_snapshot_metadata(self) -> SnapshotMetadata:
        row = self._connection.execute("SELECT data_as_of FROM order_metadata").fetchone()
        if row is None:
            return self._metadata()
        return SnapshotMetadata(datetime.fromisoformat(row[0]))

    def find_owned_order(
        self, order_id: int, principal: AuthorizedPrincipal
    ) -> OrderStatusSnapshot | None:
        if not isinstance(principal, AuthorizedPrincipal):
            return None
        row = self._connection.execute(
            "SELECT o.order_id, o.status, o.order_date, o.total_brl, o.payment_method, "
            "o.estimated_delivery FROM orders o WHERE o.order_id = ? AND o.customer_id = ?",
            (order_id, principal.customer_id),
        ).fetchone()
        if row is None:
            return None
        item_rows = self._connection.execute(
            "SELECT product_id, quantity FROM order_items WHERE order_id = ? ORDER BY product_id",
            (order_id,),
        ).fetchall()
        return OrderStatusSnapshot(
            order_id=row["order_id"], status=row["status"],
            order_date=datetime.fromisoformat(row["order_date"].replace("Z", "+00:00")),
            total_brl=Decimal(row["total_brl"]), payment_method=row["payment_method"],
            estimated_delivery=row["estimated_delivery"] or None,
            items=tuple(
                OrderItemSummary(item["product_id"], item["quantity"]) for item in item_rows
            ),
            snapshot=self.order_snapshot_metadata(),
        )

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

    def active_promotions(self, product_id: int) -> tuple[Promotion, ...]:
        rows = self._connection.execute(
            "SELECT * FROM promotions WHERE product_id = ? AND is_active = 1 ORDER BY promotion_id",
            (product_id,),
        ).fetchall()
        return tuple(
            Promotion(
                row["promotion_id"], row["product_id"], Decimal(row["discount_percent"]),
                row["description"], bool(row["is_active"]),
            )
            for row in rows
        )
