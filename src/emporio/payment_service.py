"""Deterministic promotion, payment, and shipping calculations."""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal

from .catalog import (
    AmbiguousPromotionError,
    InstallmentOption,
    PaymentCalculationError,
    PaymentResult,
    Product,
    Promotion,
)
from .catalog_repository import CatalogRepository

CENT = Decimal("0.01")


def _brl(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_EVEN)


class PaymentService:
    def __init__(self, repository: CatalogRepository) -> None:
        self._repository = repository

    def calculate(
        self,
        product_id: int,
        *,
        pix: bool = False,
        installments: int | None = None,
    ) -> PaymentResult:
        product = self._repository.find_by_id(product_id)
        if product is None:
            raise PaymentCalculationError("product was not found in the snapshot")
        promotions = self._repository.active_promotions(product_id)
        return self.calculate_for_product(product, promotions, pix=pix, installments=installments)

    @staticmethod
    def calculate_for_product(
        product: Product,
        promotions: tuple[Promotion, ...] = (),
        *,
        pix: bool = False,
        installments: int | None = None,
    ) -> PaymentResult:
        if not product.is_available:
            raise PaymentCalculationError("payment options require an available product")
        if len(promotions) > 1:
            raise AmbiguousPromotionError("multiple active promotions require manual review")
        if any(
            promotion.product_id != product.product_id
            or not promotion.is_active
            or not promotion.discount_percent.is_finite()
            or not Decimal("0") <= promotion.discount_percent <= Decimal("100")
            for promotion in promotions
        ):
            raise PaymentCalculationError("promotion does not match the available product")
        if pix and installments is not None:
            raise PaymentCalculationError("choose PIX or installments, not both")
        promotion = promotions[0] if promotions else None
        original = _brl(product.price_brl)
        discount_percent = promotion.discount_percent if promotion else None
        discount = (
            _brl(original * discount_percent / Decimal("100"))
            if promotion else Decimal("0.00")
        )
        effective = _brl(original - discount)
        pix_price = None
        pix_applied = pix and promotion is None
        if pix_applied:
            pix_price = _brl(effective * Decimal("0.95"))
        base_for_options = effective
        installment = None
        if installments is not None:
            if installments < 1 or installments > 12:
                raise PaymentCalculationError("installments must be between 1 and 12")
            if installments <= 3:
                if base_for_options < Decimal("50.00"):
                    raise PaymentCalculationError(
                        "installments require a purchase of at least R$ 50,00"
                    )
            elif installments <= 6 and base_for_options / installments < Decimal("80.00"):
                raise PaymentCalculationError(
                    "4 to 6 installments require at least R$ 80,00 per installment"
                )
            elif installments <= 12 and base_for_options / installments < Decimal("100.00"):
                raise PaymentCalculationError(
                    "7 to 12 installments require at least R$ 100,00 per installment"
                )
            installment_amount = _brl(base_for_options / installments)
            final_installment = _brl(base_for_options - installment_amount * (installments - 1))
            installment = InstallmentOption(installments, installment_amount, final_installment)
        shipping = Decimal("35.00") if effective <= Decimal("500.00") else Decimal("0.00")
        assumptions = ("Promoção e preços são baseados no snapshot operacional.",
                       "Promoção ativa impede o desconto adicional de PIX." if promotion else
                       "PIX aplica 5% com arredondamento bancário em centavos.",
                       "Frete: R$ 35,00 até R$ 500,00; grátis somente acima de R$ 500,00.")
        return PaymentResult(
            product, promotion, original, discount_percent, discount, effective, pix,
            pix_applied, pix_price, installment, shipping, product.snapshot, assumptions,
        )
