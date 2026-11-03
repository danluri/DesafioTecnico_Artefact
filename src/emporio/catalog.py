"""Domain types and errors for the operational product snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Mapping


class CatalogError(Exception):
    """Base error for catalog operations."""


class CatalogIngestionError(CatalogError):
    """Source data is invalid and was not imported."""


class CatalogQueryError(CatalogError):
    """A catalog query is invalid."""


class CatalogNotFoundError(CatalogError):
    """The requested product or snapshot does not exist."""


@dataclass(frozen=True, slots=True)
class SnapshotMetadata:
    data_as_of: datetime

    def __post_init__(self) -> None:
        if self.data_as_of.tzinfo is None:
            raise ValueError("data_as_of must be timezone-aware")

    @classmethod
    def now(cls) -> SnapshotMetadata:
        return cls(datetime.now(timezone.utc))


@dataclass(frozen=True, slots=True)
class Product:
    product_id: int
    price_brl: Decimal
    name: str
    category_id: int
    category_name: str | None
    description: str
    stock_quantity: int
    status: str
    specs: Mapping[str, object]
    created_at: str
    snapshot: SnapshotMetadata

    @property
    def is_available(self) -> bool:
        return self.status == "active" and self.stock_quantity > 0


@dataclass(frozen=True, slots=True)
class SearchCriteria:
    name: str | None = None
    category: str | None = None
    maximum_budget: Decimal | None = None
    availability_only: bool = True
    limit: int = 10
    offset: int = 0

    def __post_init__(self) -> None:
        if self.maximum_budget is not None and not self.maximum_budget.is_finite():
            raise CatalogQueryError("maximum_budget must be finite")
        if self.maximum_budget is not None and self.maximum_budget < 0:
            raise CatalogQueryError("maximum_budget cannot be negative")
        if self.limit < 1 or self.limit > 100:
            raise CatalogQueryError("limit must be between 1 and 100")
        if self.offset < 0:
            raise CatalogQueryError("offset cannot be negative")
        if (
            not any(value and value.strip() for value in (self.name, self.category))
            and self.maximum_budget is None
        ):
            raise CatalogQueryError("at least one search criterion is required")


@dataclass(frozen=True, slots=True)
class CatalogSearchResult:
    products: tuple[Product, ...]
    total: int
    criteria: SearchCriteria
    snapshot: SnapshotMetadata


@dataclass(frozen=True, slots=True)
class CatalogDetailResult:
    product: Product
    snapshot: SnapshotMetadata
