import csv
from datetime import datetime, timezone
from pathlib import Path

import pytest

from emporio.catalog import CatalogIngestionError
from emporio.catalog_sqlite import SQLiteCatalogRepository
from emporio.cli import main
from emporio.order import AuthorizedPrincipal, OrderIngestionError
from emporio.order_service import OrderService

PRODUCT_FIELDS = [
    "product_id", "price_brl", "name", "category_id", "description", "stock_quantity",
    "status", "specs", "created_at",
]
CUSTOMER_FIELDS = ["customer_id", "name", "phone", "email", "city"]
ORDER_FIELDS = [
    "order_id", "customer_id", "order_date", "status", "total_brl", "payment_method",
    "tracking_code", "estimated_delivery", "notes",
]
ITEM_FIELDS = ["order_id", "quantity", "product_id"]


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def fixture_files(tmp_path: Path, *, estimated: str = "2026-11-08") -> dict[str, Path]:
    paths = {
        name: tmp_path / f"{name}.csv"
        for name in ("products", "customers", "orders", "items")
    }
    write_csv(paths["products"], PRODUCT_FIELDS, [{
        "product_id": "7", "price_brl": "100.00", "name": "Produto sintético",
        "category_id": "1", "description": "Fixture", "stock_quantity": "2",
        "status": "active", "specs": "{}", "created_at": "2026-01-01T00:00:00Z",
    }])
    write_csv(paths["customers"], CUSTOMER_FIELDS, [{
        "customer_id": "3", "name": "Cliente Um", "phone": "00000000000",
        "email": "fixture1@example.invalid", "city": "Cidade A",
    }, {
        "customer_id": "8", "name": "Cliente Dois", "phone": "11111111111",
        "email": "fixture2@example.invalid", "city": "Cidade B",
    }])
    write_csv(paths["orders"], ORDER_FIELDS, [{
        "order_id": "1", "customer_id": "3", "order_date": "2026-11-02T12:00:00Z",
        "status": "shipped", "total_brl": "100.00", "payment_method": "pix",
        "tracking_code": "PRIVATE-TRACKING", "estimated_delivery": estimated,
        "notes": "PRIVATE NOTE",
    }, {
        "order_id": "2", "customer_id": "8", "order_date": "2026-11-02T13:00:00Z",
        "status": "pending", "total_brl": "100.00", "payment_method": "card",
        "tracking_code": "", "estimated_delivery": "", "notes": "",
    }])
    write_csv(paths["items"], ITEM_FIELDS, [
        {"order_id": "1", "quantity": "1", "product_id": "7"},
        {"order_id": "2", "quantity": "1", "product_id": "7"},
    ])
    return paths


def repository(tmp_path: Path) -> tuple[SQLiteCatalogRepository, dict[str, Path]]:
    paths = fixture_files(tmp_path)
    repo = SQLiteCatalogRepository.connect(tmp_path / "snapshot.db")
    repo.ingest(
        paths["products"], customers_csv=paths["customers"], orders_csv=paths["orders"],
        order_items_csv=paths["items"], data_as_of=datetime(2026, 11, 3, tzinfo=timezone.utc),
    )
    return repo, paths


def test_authorized_owner_gets_bounded_snapshot(tmp_path: Path) -> None:
    repo, _ = repository(tmp_path)
    result = OrderService(repo).get_status("1", AuthorizedPrincipal(3))
    assert result is not None
    assert result.status == "shipped"
    assert result.total_brl == 100
    assert result.items[0].product_id == 7
    assert result.snapshot.data_as_of.isoformat() == "2026-11-03T00:00:00+00:00"
    assert not hasattr(result, "tracking_code")
    assert not hasattr(result, "notes")


def test_refusal_paths_are_equivalent_and_non_enumerating(tmp_path: Path) -> None:
    repo, _ = repository(tmp_path)
    service = OrderService(repo)
    outcomes = [
        service.get_status("1", None),
        service.get_status("1", AuthorizedPrincipal(8)),
        service.get_status("999", AuthorizedPrincipal(3)),
        service.get_status("not-an-id", AuthorizedPrincipal(3)),
        service.get_status("-1", AuthorizedPrincipal(3)),
        service.get_status("999999999999999999999", AuthorizedPrincipal(3)),
    ]
    assert outcomes == [None] * len(outcomes)
    assert OrderService.safe_message() == OrderService.safe_message()


def test_missing_optional_delivery_is_explicit(tmp_path: Path) -> None:
    repo, paths = repository(tmp_path)
    write_csv(paths["orders"], ORDER_FIELDS, [{
        "order_id": "1", "customer_id": "3", "order_date": "2026-11-02T12:00:00Z",
        "status": "delivered", "total_brl": "100.00", "payment_method": "pix",
        "tracking_code": "", "estimated_delivery": "", "notes": "",
    }, {
        "order_id": "2", "customer_id": "8", "order_date": "2026-11-02T13:00:00Z",
        "status": "pending", "total_brl": "100.00", "payment_method": "card",
        "tracking_code": "", "estimated_delivery": "", "notes": "",
    }])
    repo.ingest(paths["products"], customers_csv=paths["customers"], orders_csv=paths["orders"],
                order_items_csv=paths["items"])
    result = OrderService(repo).get_status(1, AuthorizedPrincipal(3))
    assert result is not None
    assert result.estimated_delivery is None
    assert "não estão disponíveis" in result.tracking_message


def test_invalid_order_source_rolls_back_previous_snapshot(tmp_path: Path) -> None:
    repo, paths = repository(tmp_path)
    write_csv(
        paths["items"], ITEM_FIELDS,
        [{"order_id": "404", "quantity": "1", "product_id": "7"}],
    )
    with pytest.raises((OrderIngestionError, CatalogIngestionError)):
        repo.ingest(paths["products"], customers_csv=paths["customers"], orders_csv=paths["orders"],
                    order_items_csv=paths["items"])
    assert OrderService(repo).get_status(1, AuthorizedPrincipal(3)) is not None


def test_cli_order_status_is_explicit_and_private(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo, paths = repository(tmp_path)
    result = main([
        "--catalog-action", "order-status", "--catalog-db", str(tmp_path / "snapshot.db"),
        "--order", "1", "--demo-server-principal", "3",
    ])
    output = capsys.readouterr().out
    assert result == 0
    assert "Pedido 1" in output
    assert "não é rastreamento em tempo real" in output
    assert "PRIVATE-TRACKING" not in output
    assert "PRIVATE NOTE" not in output
    assert "fixture1@example.invalid" not in output
    assert paths["products"].exists()


def test_cli_refusal_does_not_disclose_existence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repository(tmp_path)
    assert main([
        "--catalog-action", "order-status", "--catalog-db", str(tmp_path / "snapshot.db"),
        "--order", "1",
    ]) == 0
    anonymous = capsys.readouterr().out
    assert main([
        "--catalog-action", "order-status", "--catalog-db", str(tmp_path / "snapshot.db"),
        "--order", "999", "--demo-server-principal", "3",
    ]) == 0
    missing = capsys.readouterr().out
    assert anonymous == missing
