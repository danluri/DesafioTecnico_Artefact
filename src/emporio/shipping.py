"""Deterministic shipping policy analysis; no carrier network calls are made."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from .catalog import PaymentCalculationError, Product


class ShippingAnalysisError(PaymentCalculationError):
    """Shipping input is incomplete or outside the declared policy."""


@dataclass(frozen=True, slots=True)
class Package:
    weight_kg: Decimal
    length_cm: Decimal
    width_cm: Decimal
    height_cm: Decimal

    def __post_init__(self) -> None:
        values = (self.weight_kg, self.length_cm, self.width_cm, self.height_cm)
        if any(
            not isinstance(value, Decimal) or not value.is_finite() or value <= 0
            for value in values
        ):
            raise ShippingAnalysisError("package weight and dimensions are required")

    @property
    def volume_cm3(self) -> Decimal:
        return self.length_cm * self.width_cm * self.height_cm


@dataclass(frozen=True, slots=True)
class ShippingOption:
    carrier: str
    service: str
    price_brl: Decimal | None
    deadline_days: int | None
    insurance_brl: Decimal | None
    tracking: bool
    simulated: bool
    provenance: str


@dataclass(frozen=True, slots=True)
class ShippingAnalysis:
    destination: str
    local: bool
    complete: bool
    options: tuple[ShippingOption, ...]
    message: str
    provenance: str = "synthetic store policy"


class ShippingService:
    """Apply local Campo Grande rules or deterministic remote estimates."""

    def analyze_product(
        self,
        product: Product,
        destination: str,
        *,
        order_total: Decimal,
        cep: str | None = None,
    ) -> ShippingAnalysis:
        values = (
            product.package_weight_kg,
            product.package_length_cm,
            product.package_width_cm,
            product.package_height_cm,
        )
        package = Package(*values) if all(value is not None for value in values) else None
        return self.analyze(destination, order_total=order_total, package=package, cep=cep)

    def analyze(
        self,
        destination: str,
        *,
        order_total: Decimal,
        package: Package | None = None,
        cep: str | None = None,
    ) -> ShippingAnalysis:
        if not isinstance(destination, str) or not destination.strip():
            raise ShippingAnalysisError("destination is required")
        total = Decimal(order_total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if total < 0:
            raise ShippingAnalysisError("order total cannot be negative")
        local = destination.strip().casefold() in {
            "campo grande", "campo grande - ms", "campo grande/ms"
        }
        if local:
            price = Decimal("35.00") if total <= Decimal("500.00") else Decimal("0.00")
            option = ShippingOption(
                "Emporio", "entrega local", price, 2, None, False, True,
                "synthetic store policy",
            )
            return ShippingAnalysis(
                destination.strip(), True, True, (option,),
                "Entrega local conforme a pol\u00edtica de Campo Grande.",
            )
        if not isinstance(cep, str) or not re.fullmatch(r"\d{8}", cep.replace("-", "")):
            return ShippingAnalysis(
                destination.strip(), False, False, (),
                "CEP v\u00e1lido \u00e9 necess\u00e1rio para calcular o frete.",
            )
        if package is None:
            return ShippingAnalysis(
                destination.strip(), False, False, (),
                "Peso e dimens\u00f5es do pacote s\u00e3o necess\u00e1rios para calcular o frete.",
            )
        largest_dimension = max(package.length_cm, package.width_cm, package.height_cm)
        if package.weight_kg > Decimal("30") or largest_dimension > Decimal("100"):
            quote = ShippingOption(
                "A cotar", "frete especial", None, None, None, False, True,
                "synthetic policy; carrier quote required",
            )
            return ShippingAnalysis(
                destination.strip(), False, True, (quote,),
                "O pacote exige cota\u00e7\u00e3o especial; nenhum valor foi inventado.",
            )
        base = Decimal("24.90") + package.weight_kg * Decimal("2.50")
        pac = ShippingOption(
            "Correios", "PAC", base.quantize(Decimal("0.01")), 8,
            Decimal("0.50"), True, True, "synthetic Correios estimate",
        )
        sedex = ShippingOption(
            "Correios", "SEDEX", (base + Decimal("18.00")).quantize(Decimal("0.01")), 4,
            Decimal("0.50"), True, True, "synthetic Correios estimate",
        )
        jadlog = ShippingOption(
            "Jadlog", "Package", (base - Decimal("3.00")).quantize(Decimal("0.01")), 7,
            Decimal("0.50"), True, True, "synthetic Jadlog estimate",
        )
        return ShippingAnalysis(
            destination.strip(), False, True, (pac, sedex, jadlog),
            "Op\u00e7\u00f5es simuladas; confirme o prazo e o pre\u00e7o antes do pagamento.",
        )


analyze_shipping = ShippingService().analyze
