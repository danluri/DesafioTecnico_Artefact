"""Typed repository boundary for operational catalog facts."""

from __future__ import annotations

from typing import Protocol

from .catalog import Product, Promotion, SearchCriteria, SnapshotMetadata


class CatalogRepository(Protocol):
    def search(self, criteria: SearchCriteria) -> tuple[tuple[Product, ...], int, SnapshotMetadata]:
        """Return a bounded page, total count, and snapshot metadata."""

    def find_by_id(self, product_id: int) -> Product | None:
        """Return a product by its preserved source ID."""

    def find_by_name(self, name: str) -> tuple[Product, ...]:
        """Return exact normalized name matches in deterministic order."""

    def active_promotions(self, product_id: int) -> tuple[Promotion, ...]:
        """Return active snapshot promotions for a product in promotion-ID order."""
