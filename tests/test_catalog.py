import csv
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from emporio.catalog import CatalogIngestionError, CatalogQueryError
from emporio.catalog_service import CatalogService
from emporio.catalog_sqlite import SQLiteCatalogRepository
from emporio.cli import main

FIELDS = [
    "product_id",
    "price_brl",
    "name",
    "category_id",
    "description",
    "stock_quantity",
    "status",
    "specs",
    "created_at",
]


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def write_categories(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["category_id", "name", "description"])
        writer.writeheader()
        writer.writerows(rows)


def row(
    product_id: str,
    name: str,
    price: str = "1500.50",
    stock: str = "2",
    status: str = "active",
    category_id: str = "1",
) -> dict[str, str]:
    return {
        "product_id": product_id,
        "price_brl": price,
        "name": name,
        "category_id": category_id,
        "description": "Instrumento de teste",
        "stock_quantity": stock,
        "status": status,
        "specs": '{"color": "natural"}',
        "created_at": "2026-01-01T00:00:00Z",
    }


@pytest.fixture
def catalog(tmp_path: Path) -> tuple[SQLiteCatalogRepository, Path]:
    source = tmp_path / "products.csv"
    write_csv(
        source,
        [
            row("2", "Violão", "1500.50", "4"),
            row("1", "Baixo", "900.00", "0"),
            row("3", "Teclado", "2200.00", "2", "discontinued"),
        ],
    )
    repository = SQLiteCatalogRepository.connect(tmp_path / "catalog.db")
    repository.ingest(source, data_as_of=datetime(2026, 11, 2, tzinfo=timezone.utc))
    return repository, source


def test_ingestion_filters_availability_orders_and_paginates(
    catalog: tuple[SQLiteCatalogRepository, Path],
) -> None:
    repository, _ = catalog
    result = CatalogService(repository).search(category="1", limit=1)
    assert [product.name for product in result.products] == ["Violão"]
    assert result.total == 1
    assert result.products[0].price_brl == Decimal("1500.50")
    assert result.products[0].is_available


def test_detail_uses_stored_fields_and_snapshot(
    catalog: tuple[SQLiteCatalogRepository, Path],
) -> None:
    repository, _ = catalog
    result = CatalogService(repository).detail("2")
    assert result.product.name == "Violão"
    assert result.product.price_brl == Decimal("1500.50")
    assert result.snapshot.data_as_of.year == 2026


def test_no_match_and_ambiguous_name_are_safe(tmp_path: Path) -> None:
    source = tmp_path / "products.csv"
    write_csv(source, [row("1", "Piano"), row("2", "Piano")])
    repository = SQLiteCatalogRepository.connect(tmp_path / "catalog.db")
    repository.ingest(source)
    service = CatalogService(repository)
    assert service.detail("guitarra") == ()
    assert len(service.detail("Piano")) == 2


def test_invalid_ingestion_is_atomic(catalog: tuple[SQLiteCatalogRepository, Path]) -> None:
    repository, source = catalog
    write_csv(source, [row("2", "Violão"), row("2", "Duplicado")])
    with pytest.raises(CatalogIngestionError):
        repository.ingest(source)
    assert repository.find_by_id(2).name == "Violão"
    assert repository.find_by_id(1).name == "Baixo"


def test_query_requires_criteria() -> None:
    with pytest.raises(CatalogQueryError):
        CatalogService(object()).search()


def test_budget_boundaries_and_comma_input(catalog: tuple[SQLiteCatalogRepository, Path]) -> None:
    repository, _ = catalog
    service = CatalogService(repository)
    result = service.search(maximum_budget="1.500,50")
    assert [product.product_id for product in result.products] == [2]
    for invalid in ("NaN", "Infinity", "-1"):
        with pytest.raises(CatalogQueryError):
            service.search(maximum_budget=invalid)


def test_pagination_is_ordered_and_bounded(tmp_path: Path) -> None:
    source = tmp_path / "products.csv"
    write_csv(source, [row("3", "C"), row("1", "A"), row("2", "B")])
    repository = SQLiteCatalogRepository.connect(tmp_path / "catalog.db")
    repository.ingest(source)
    result = CatalogService(repository).search(name="", category="1", limit=1, offset=1)
    assert [product.name for product in result.products] == ["B"]
    assert result.total == 3


def test_cli_detail_success_includes_specs(
    catalog: tuple[SQLiteCatalogRepository, Path],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, _ = catalog
    result = main(
        [
            "--catalog-action", "detail", "--catalog-db", str(tmp_path / "catalog.db"),
            "--product", "2",
        ]
    )
    output = capsys.readouterr().out
    assert result == 0
    assert "Especifica" in output
    assert "color: natural" in output


def test_cli_detail_ambiguity_and_no_match(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "products.csv"
    write_csv(source, [row("1", "Piano"), row("2", "Piano")])
    db = tmp_path / "catalog.db"
    repository = SQLiteCatalogRepository.connect(db)
    repository.ingest(source)
    assert main(["--catalog-action", "detail", "--catalog-db", str(db), "--product", "Piano"]) == 0
    assert "mais de um" in capsys.readouterr().out
    assert main(["--catalog-action", "detail", "--catalog-db", str(db), "--product", "Órgão"]) == 0
    assert "encontrei" in capsys.readouterr().out.lower()


def test_cli_catalog_connection_error_is_safe(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = main(
        [
            "--catalog-action", "detail", "--catalog-db", str(tmp_path / "missing" / "catalog.db"),
            "--product", "1",
        ]
    )
    output = capsys.readouterr().out
    assert result == 2
    assert "cat\u00e1logo" in output
    assert "manual" not in output
    assert "Traceback" not in output


@pytest.mark.parametrize(
    "variant",
    [
        "duplicate_header",
        "extra_column",
        "malformed_row",
        "bad_status",
        "bad_date",
        "extreme_price",
    ],
)
def test_invalid_source_variants_are_rejected(tmp_path: Path, variant: str) -> None:
    source = tmp_path / "products.csv"
    if variant == "duplicate_header":
        source.write_text(",".join(FIELDS[:-1] + ["name", "created_at"]) + "\n", encoding="utf-8")
    elif variant == "extra_column":
        source.write_text(",".join(FIELDS + ["unexpected"]) + "\n", encoding="utf-8")
    else:
        item = row("1", "Piano")
        if variant == "malformed_row":
            source.write_text(
                ",".join(FIELDS) + "\n" + ",".join(item[field] for field in FIELDS) + ",extra\n",
                encoding="utf-8",
            )
        else:
            if variant == "bad_status":
                item["status"] = "ACTIVE"
            if variant == "bad_date":
                item["created_at"] = "not-a-date"
            if variant == "extreme_price":
                item["price_brl"] = "1e999999"
            write_csv(source, [item])
    repository = SQLiteCatalogRepository.connect(tmp_path / "catalog.db")
    with pytest.raises(CatalogIngestionError):
        repository.ingest(source)


def test_category_csv_validation(tmp_path: Path) -> None:
    products = tmp_path / "products.csv"
    categories = tmp_path / "categories.csv"
    write_csv(products, [row("1", "Piano", category_id="2")])
    write_categories(categories, [{"category_id": "1", "name": "Cordas", "description": ""}])
    repository = SQLiteCatalogRepository.connect(tmp_path / "catalog.db")
    with pytest.raises(CatalogIngestionError):
        repository.ingest(products, categories)


def test_naive_snapshot_timestamp_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "products.csv"
    write_csv(source, [row("1", "Piano")])
    repository = SQLiteCatalogRepository.connect(tmp_path / "catalog.db")
    with pytest.raises(CatalogIngestionError):
        repository.ingest(source, data_as_of=datetime(2026, 11, 2))


def test_insertion_failure_rolls_back_previous_snapshot(
    catalog: tuple[SQLiteCatalogRepository, Path],
) -> None:
    repository, source = catalog
    repository._connection.execute(
        "CREATE TRIGGER reject_product BEFORE INSERT ON products WHEN NEW.product_id = 99 "
        "BEGIN SELECT RAISE(ABORT, 'test failure'); END;"
    )
    write_csv(source, [row("99", "Rejected")])
    with pytest.raises(CatalogIngestionError):
        repository.ingest(source)
    assert repository.find_by_id(2) is not None
    assert repository.find_by_id(99) is None


def test_cli_catalog_search_renders_snapshot_price(
    catalog: tuple[SQLiteCatalogRepository, Path],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, source = catalog

    result = main(
        [
            "--catalog-action",
            "search",
            "--catalog-db",
            str(tmp_path / "catalog.db"),
            "--products-csv",
            str(source),
            "--name",
            "Violão",
        ]
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "R$ 1.500,50" in output
    assert "não é estoque em tempo real" in output
