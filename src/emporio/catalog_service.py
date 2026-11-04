"""Deterministic customer-facing catalog use cases."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from dataclasses import replace
import re

from .catalog import (
    CatalogDetailResult,
    CatalogQueryError,
    CatalogSearchResult,
    Product,
    SearchCriteria,
)
from .catalog_repository import CatalogRepository
from .catalog_search import search_filters


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
        return CatalogSearchResult(products, total, criteria, snapshot)

    def detail(self, reference: str) -> CatalogDetailResult | tuple[Product, ...]:
        if not reference or not reference.strip():
            raise CatalogQueryError("product reference cannot be empty")
        value = reference.strip()
        if value.isdigit():
            product = self._repository.find_by_id(int(value))
            return CatalogDetailResult(product, product.snapshot) if product else ()
        matches = self._repository.find_by_name(value)
        if len(matches) == 1:
            return CatalogDetailResult(matches[0], matches[0].snapshot)
        return matches
