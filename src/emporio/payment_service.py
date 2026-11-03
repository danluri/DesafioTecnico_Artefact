"""Deterministic promotion, payment, and shipping calculations."""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal

from .catalog import (
    AmbiguousPromotionError,
    InstallmentOption,
    PaymentCalculationError,
    PaymentCombination,
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

    def calculate_combinations(
        self,
        product_id: int,
        *,
        pix_percent: Decimal = Decimal("0.20"),
        installments: tuple[int, ...] = (1, 3, 6, 12),
    ) -> tuple[PaymentCombination, ...]:
        """Return market-style split payments for an eligible non-promotional total."""
        product = self._repository.find_by_id(product_id)
        if product is None:
            raise PaymentCalculationError("product was not found in the snapshot")
        promotions = self._repository.active_promotions(product_id)
        if promotions:
            raise PaymentCalculationError("PIX split is not available with a promotion")
        return self.calculate_combinations_for_total(
            product.price_brl, pix_percent=pix_percent, installments=installments
        )

    @staticmethod
    def calculate_combinations_for_total(
        total: Decimal,
        *,
        pix_percent: Decimal = Decimal("0.20"),
        installments: tuple[int, ...] = (1, 3, 6, 12),
    ) -> tuple[PaymentCombination, ...]:
        total = _brl(total)
        pix_percent = Decimal(pix_percent)
        if total <= Decimal("2000.00"):
            raise PaymentCalculationError("PIX split requires a total above R$ 2.000,00")
        if not pix_percent.is_finite() or not Decimal("0") < pix_percent < Decimal("1"):
            raise PaymentCalculationError("PIX split percentage must be between 0 and 1")
        if not installments or len(set(installments)) != len(installments):
            raise PaymentCalculationError("installment options are invalid")
        pix_amount = _brl(total * pix_percent)
        card_amount = _brl(total - pix_amount)
        options: list[PaymentCombination] = []
        for count in installments:
            if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 12:
                raise PaymentCalculationError("installments must be between 1 and 12")
            if card_amount / count < Decimal("100.00"):
                continue
            amount = _brl(card_amount / count)
            final = _brl(card_amount - amount * (count - 1))
            option = InstallmentOption(count, amount, final)
            options.append(PaymentCombination(
                pix_amount, card_amount, option, total,
                f"{pix_amount} no PIX + {card_amount} no cartão em {count}x",
            ))
        if not options:
            raise PaymentCalculationError("no valid card installment remains after the PIX split")
        return tuple(options)

    combinations = calculate_combinations

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
