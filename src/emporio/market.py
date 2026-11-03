"""Optional exact-match market observations, separate from the official catalog."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol
from urllib.parse import urlsplit

from .catalog import Product


@dataclass(frozen=True, slots=True)
class ExternalOffer:
    retailer: str
    url: str
    price_brl: Decimal
    observed_on: date
    condition: str
    match_information: str
    product_id: int
    is_exact: bool = False
    provider: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.is_exact, bool) or not isinstance(self.provider, str):
            raise ValueError("market match fields have invalid types")
        if not self.provider.strip() or not self.retailer.strip():
            raise ValueError("market provider and retailer are required")
        parsed = urlsplit(self.url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("market offer URL must be HTTPS")
        if not self.price_brl.is_finite() or self.price_brl < 0:
            raise ValueError("market offer price must be finite and non-negative")


class ExternalOfferPort(Protocol):
    def offers_for(self, product: Product) -> tuple[ExternalOffer, ...]: ...


class ExactMatchMarketService:
    def __init__(self, provider: ExternalOfferPort, minimum_offers: int = 2) -> None:
        self.provider = provider
        self.minimum_offers = minimum_offers

    def compare(self, product: Product) -> tuple[ExternalOffer, ...]:
        offers = self.provider.offers_for(product)
        matches = tuple(
            offer
            for offer in offers
            if offer.product_id == product.product_id
            and offer.is_exact
            and bool(offer.provider.strip())
            and offer.condition.strip().lower() == "new"
        )
        if len({offer.provider.casefold() for offer in matches}) < self.minimum_offers:
            return ()
        return matches


class FakeExternalOfferProvider:
    def __init__(self, offers: tuple[ExternalOffer, ...] = ()) -> None:
        self.offers = offers

    def offers_for(self, product: Product) -> tuple[ExternalOffer, ...]:
        return tuple(offer for offer in self.offers if offer.product_id == product.product_id)
