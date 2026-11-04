"""Deterministic customer-facing catalog use cases."""

from __future__ import annotations

import re
from dataclasses import replace
from decimal import Decimal, InvalidOperation

from .catalog import (
    CatalogDetailResult,
    CatalogQueryError,
    CatalogSearchResult,
    Product,
    Promotion,
    SearchCriteria,
)
from .catalog_repository import CatalogRepository
from .catalog_search import search_filters

MAX_ALTERNATIVES = 3


class CatalogService:
    def __init__(self, repository: CatalogRepository) -> None:
        self._repository = repository

    def search(
        self,
        *,
        name: str | None = None,
        category: str | None = None,
        maximum_budget: str | Decimal | None = None,
        limit: int = 10,
        offset: int = 0,
        availability_only: bool = True,
    ) -> CatalogSearchResult:
        original_name, original_category = name, category
        name, category = search_filters(name, category)
        budget = None
        if maximum_budget is not None and str(maximum_budget).strip():
            try:
                raw_budget = str(maximum_budget).strip()
                raw_budget = re.sub(r'^R\$\s*', '', raw_budget, flags=re.IGNORECASE)
                if "," in raw_budget:
                    raw_budget = raw_budget.replace(".", "").replace(",", ".")
                elif re.fullmatch(r'\d{1,3}(?:\.\d{3})+', raw_budget):
                    raw_budget = raw_budget.replace('.', '')
                budget = Decimal(raw_budget)
            except (InvalidOperation, ValueError) as exc:
                raise CatalogQueryError("maximum_budget must be a valid amount") from exc
            if not budget.is_finite() or budget < 0:
                raise CatalogQueryError("maximum_budget must be finite and non-negative")
        criteria = SearchCriteria(
            name=name,
            category=category,
            maximum_budget=budget,
            limit=limit,
            offset=offset,
            availability_only=availability_only,
        )
        products, total, snapshot = self._repository.search(criteria)
        if total == 0 and original_name and not original_category and name is None:
            # Legacy snapshots may lack category labels but use the instrument as its name.
            criteria = replace(criteria, name=original_name, category=None)
            products, total, snapshot = self._repository.search(criteria)
        alternatives: tuple[Product, ...] = ()
        if total == 0 and criteria.name and criteria.availability_only:
            # A named product that exists but cannot be sold must not look nonexistent
            # (manual 7.3): return it flagged, with available alternatives.
            unavailable = replace(criteria, availability_only=False)
            products, total, snapshot = self._repository.search(unavailable)
            if total:
                criteria = unavailable
                alternatives = self._alternatives(products)
        return CatalogSearchResult(
            products, total, criteria, snapshot, alternatives, self._expired_promotions(products)
        )

    def detail(self, reference: str) -> CatalogDetailResult | tuple[Product, ...]:
        if not reference or not reference.strip():
            raise CatalogQueryError("product reference cannot be empty")
        value = reference.strip()
        if value.isdigit():
            product = self._repository.find_by_id(int(value))
            return self._detail(product) if product else ()
        matches = self._repository.find_by_name(value)
        if len(matches) == 1:
            return self._detail(matches[0])
        return matches

    def _detail(self, product: Product) -> CatalogDetailResult:
        alternatives = () if product.is_available else self._alternatives((product,))
        return CatalogDetailResult(
            product, product.snapshot, alternatives,
            self._repository.inactive_promotions(product.product_id),
        )

    def _alternatives(self, unavailable: tuple[Product, ...]) -> tuple[Product, ...]:
        """Available products in the same category, closest in price to the requested one."""
        reference = unavailable[0] if unavailable else None
        if reference is None or not reference.category_name:
            return ()
        criteria = SearchCriteria(category=reference.category_name, limit=100)
        candidates, _total, _snapshot = self._repository.search(criteria)
        excluded = {product.product_id for product in unavailable}
        ranked = sorted(
            (product for product in candidates if product.product_id not in excluded),
            key=lambda product: (abs(product.price_brl - reference.price_brl), product.product_id),
        )
        return tuple(ranked[:MAX_ALTERNATIVES])

    def _expired_promotions(
        self, products: tuple[Product, ...]
    ) -> dict[int, tuple[Promotion, ...]]:
        found = {p.product_id: self._repository.inactive_promotions(p.product_id) for p in products}
        return {product_id: promotions for product_id, promotions in found.items() if promotions}
