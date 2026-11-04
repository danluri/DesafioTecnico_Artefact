"""Domain types and errors for the operational product snapshot."""

from __future__ import annotations

from dataclasses import dataclass, field
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


class PromotionError(CatalogError):
    """A promotion cannot be safely applied."""


class AmbiguousPromotionError(PromotionError):
    """More than one active promotion applies to a product."""


class PaymentCalculationError(CatalogError):
    """A payment option is invalid or unsupported by the declared policy."""


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
    package_weight_kg: Decimal | None = None
    package_length_cm: Decimal | None = None
    package_width_cm: Decimal | None = None
    package_height_cm: Decimal | None = None

    @property
    def is_available(self) -> bool:
        return self.status == "active" and self.stock_quantity > 0

    @property
    def availability(self) -> str:
        """Customer-facing availability code used by the policy guidance below."""
        if self.status == "discontinued":
            return "discontinued"
        if self.status == "coming_soon":
            return "coming_soon"
        return "available" if self.stock_quantity > 0 else "out_of_stock"


# Manual de políticas, seção 7.3 (Situações Especiais). Sent with tool results so the
# model applies the rule; facts (stock, status, alternatives) come from the snapshot.
AVAILABILITY_GUIDANCE = {
    "out_of_stock": (
        "Produto temporariamente indisponível (sem estoque no sistema). Informe isso e "
        "sugira as alternativas disponíveis listadas. Nunca confirme disponibilidade."
    ),
    "discontinued": (
        "Produto descontinuado: não faz mais parte do catálogo. Informe isso e ofereça "
        "os modelos equivalentes listados."
    ),
    "coming_soon": (
        "Produto ainda não lançado (em breve): não está disponível para compra. "
        "Ofereça as alternativas disponíveis listadas."
    ),
}

EXPIRED_PROMOTION_GUIDANCE = (
    "Promoção vencida: não está mais ativa no sistema. Se o cliente perguntar, informe "
    "com transparência e apresente o preço atual. Nunca prometa esse desconto."
)


@dataclass(frozen=True, slots=True)
class Promotion:
    promotion_id: int
    product_id: int
    discount_percent: Decimal
    description: str
    is_active: bool


@dataclass(frozen=True, slots=True)
class InstallmentOption:
    count: int
    amount_brl: Decimal
    final_amount_brl: Decimal


@dataclass(frozen=True, slots=True)
class PaymentResult:
    product: Product
    promotion: Promotion | None
    original_price_brl: Decimal
    discount_percent: Decimal | None
    discount_brl: Decimal
    effective_price_brl: Decimal
    pix_requested: bool
    pix_applied: bool
    pix_price_brl: Decimal | None
    installments: InstallmentOption | None
    shipping_brl: Decimal
    snapshot: SnapshotMetadata
    assumptions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PaymentCombination:
    """A deterministic PIX deposit plus card remainder option."""

    pix_amount_brl: Decimal
    card_amount_brl: Decimal
    installments: InstallmentOption
    total_brl: Decimal
    description: str


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
    # Available products suggested when the matched products cannot be sold.
    alternatives: tuple[Product, ...] = ()
    # Inactive promotions by product ID, so the agent never offers an expired discount.
    expired_promotions: Mapping[int, tuple[Promotion, ...]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CatalogDetailResult:
    product: Product
    snapshot: SnapshotMetadata
    alternatives: tuple[Product, ...] = ()
    expired_promotions: tuple[Promotion, ...] = ()
