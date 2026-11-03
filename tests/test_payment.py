import csv
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from emporio.catalog import (
    AmbiguousPromotionError,
    CatalogIngestionError,
    PaymentCalculationError,
)
from emporio.catalog_sqlite import SQLiteCatalogRepository
from emporio.cli import main
from emporio.payment_service import PaymentService

PRODUCT_FIELDS = [
    "product_id", "price_brl", "name", "category_id", "description", "stock_quantity",
    "status", "specs", "created_at",
]
PROMOTION_FIELDS = ["promotion_id", "product_id", "discount_percent", "description", "is_active"]


def write_rows(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def product(product_id: str = "1", price: str = "1000.00") -> dict[str, str]:
    return {
        "product_id": product_id, "price_brl": price, "name": "Piano",
        "category_id": "1", "description": "Teste", "stock_quantity": "2",
        "status": "active", "specs": "{}", "created_at": "2026-01-01T00:00:00Z",
    }


def promotion(
    promotion_id: str, product_id: str = "1", discount: str = "10", active: str = "1"
) -> dict[str, str]:
    return {
        "promotion_id": promotion_id, "product_id": product_id,
        "discount_percent": discount, "description": "Oferta", "is_active": active,
    }


def repository(tmp_path: Path, price: str = "1000.00") -> tuple[SQLiteCatalogRepository, Path]:
    products = tmp_path / "products.csv"
    promotions = tmp_path / "promotions.csv"
    write_rows(products, PRODUCT_FIELDS, [product(price=price)])
    write_rows(promotions, PROMOTION_FIELDS, [promotion("1")])
    repo = SQLiteCatalogRepository.connect(tmp_path / "catalog.db")
    repo.ingest(products, promotions_csv=promotions,
                data_as_of=datetime(2026, 11, 3, tzinfo=timezone.utc))
    return repo, promotions


def test_active_promotion_is_separate_and_pix_does_not_stack(tmp_path: Path) -> None:
    repo, _ = repository(tmp_path)
    result = PaymentService(repo).calculate(1, pix=True)
    assert result.original_price_brl == Decimal("1000.00")
    assert result.discount_brl == Decimal("100.00")
    assert result.effective_price_brl == Decimal("900.00")
    assert not result.pix_applied
    assert result.pix_price_brl is None


def test_non_promotional_pix_uses_banker_rounding(tmp_path: Path) -> None:
    repo, promotions = repository(tmp_path, price="100.05")
    write_rows(promotions, PROMOTION_FIELDS, [promotion("1", active="0")])
    repo.ingest(tmp_path / "products.csv", promotions_csv=promotions)
    result = PaymentService(repo).calculate(1, pix=True)
    assert result.pix_price_brl == Decimal("95.05")


def test_promotional_rounding_and_shipping_use_effective_order_total(tmp_path: Path) -> None:
    repo, _ = repository(tmp_path, price="501.00")
    result = PaymentService(repo).calculate(1)

    assert result.discount_brl == Decimal("50.10")
    assert result.effective_price_brl == Decimal("450.90")
    assert result.shipping_brl == Decimal("35.00")


@pytest.mark.parametrize(
    "amount, count, expected",
    [(500, 5, Decimal("100.00")), (1200, 12, Decimal("100.00"))],
)
def test_installment_boundaries(tmp_path: Path, amount: int, count: int, expected: Decimal) -> None:
    repo, promotions = repository(tmp_path, price=str(amount))
    write_rows(promotions, PROMOTION_FIELDS, [promotion("1", active="0")])
    repo.ingest(tmp_path / "products.csv", promotions_csv=promotions)
    result = PaymentService(repo).calculate(1, installments=count)
    assert result.installments.amount_brl == expected
    assert result.installments.final_amount_brl == expected


def test_installments_reject_invalid_band(tmp_path: Path) -> None:
    repo, _ = repository(tmp_path, price="49.99")
    with pytest.raises(PaymentCalculationError):
        PaymentService(repo).calculate(1, installments=1)
    with pytest.raises(PaymentCalculationError):
        PaymentService(repo).calculate(1, installments=13)


@pytest.mark.parametrize(
    "price, shipping", [("500.00", Decimal("35.00")), ("500.01", Decimal("0.00"))]
)
def test_shipping_boundary(tmp_path: Path, price: str, shipping: Decimal) -> None:
    repo, promotions = repository(tmp_path, price=price)
    write_rows(promotions, PROMOTION_FIELDS, [promotion("1", active="0")])
    repo.ingest(tmp_path / "products.csv", promotions_csv=promotions)
    assert PaymentService(repo).calculate(1).shipping_brl == shipping


def test_multiple_active_promotions_are_ambiguous(tmp_path: Path) -> None:
    products = tmp_path / "products.csv"
    promotions = tmp_path / "promotions.csv"
    write_rows(products, PRODUCT_FIELDS, [product()])
    write_rows(promotions, PROMOTION_FIELDS, [promotion("1"), promotion("2", discount="20")])
    repo = SQLiteCatalogRepository.connect(tmp_path / "catalog.db")
    repo.ingest(products, promotions_csv=promotions)
    with pytest.raises(AmbiguousPromotionError):
        PaymentService(repo).calculate(1)


@pytest.mark.parametrize("discount", ["-1", "100.01", "NaN", "Infinity"])
def test_invalid_promotion_is_rejected_atomically(tmp_path: Path, discount: str) -> None:
    repo, promotions = repository(tmp_path)
    write_rows(promotions, PROMOTION_FIELDS, [promotion("1", discount=discount)])
    with pytest.raises(CatalogIngestionError):
        repo.ingest(tmp_path / "products.csv", promotions_csv=promotions)
    assert repo.active_promotions(1)[0].discount_percent == Decimal("10.00")


def test_cli_payment_renders_components_and_snapshot(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo, promotions = repository(tmp_path)
    result = main(
        [
            "--catalog-action",
            "payment",
            "--catalog-db",
            str(tmp_path / "catalog.db"),
            "--product",
            "1",
            "--pix",
            "--promotions-csv",
            str(promotions),
        ]
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "Preço original" in output
    assert "Desconto de promoção" in output
    assert "Preço efetivo" in output
    assert "sem acúmulo com promoção" in output
    assert "Frete" in output
    assert "Snapshot" in output
    assert repo.active_promotions(1)
