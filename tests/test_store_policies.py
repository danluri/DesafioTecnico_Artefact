"""Manual sections 7.1 and 7.3: out-of-stock, discontinued, expired promotions, business hours."""

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from test_catalog import row, write_categories, write_csv

from emporio.catalog_service import CatalogService
from emporio.catalog_sqlite import SQLiteCatalogRepository
from emporio.conversation import ConversationService
from emporio.llm import FakeLLM
from emporio.payment_service import PaymentService
from emporio.session_service import SessionService
from emporio.session_sqlite import SQLiteSessionRepository
from emporio.store_hours import STORE_TZ, is_open, out_of_hours_notice
from emporio.tools import ToolRegistry


@pytest.fixture
def repository(tmp_path: Path) -> SQLiteCatalogRepository:
    products = tmp_path / "products.csv"
    write_csv(products, [
        row("1", "Giannini GF-3D Dreadnought", "799.90", "0", category_id="5"),
        row("2", "Shelby SN-7C Nylon", "749.00", "0", "discontinued", category_id="5"),
        row("3", "Ibanez Bass 2X", "441.00", "13", "discontinued", category_id="2"),
        row("4", "Yamaha C40", "599.90", "5", category_id="5"),
        row("5", "Takamine GD20 Dreadnought", "2199.00", "5", category_id="5"),
        row("6", "Giannini GF-1R Folk", "579.90", "7", category_id="5"),
        row("7", "Kala Barítono", "1749.00", "2", "coming_soon", category_id="9"),
    ])
    categories = tmp_path / "categories.csv"
    write_categories(categories, [
        {"category_id": "2", "name": "Baixos", "description": "Baixos"},
        {"category_id": "5", "name": "Violões", "description": "Violões"},
        {"category_id": "9", "name": "Ukuleles", "description": "Ukuleles"},
    ])
    promotions = tmp_path / "promotions.csv"
    with promotions.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["promotion_id", "product_id", "discount_percent", "description", "is_active"]
        )
        writer.writerow(["4", "5", "12", "Oferta Especial", "0"])
    repo = SQLiteCatalogRepository.connect(tmp_path / "catalog.db")
    as_of = datetime(2026, 11, 4, tzinfo=timezone.utc)
    repo.ingest(products, categories, promotions, data_as_of=as_of)
    return repo


def _tool_value(repository, tool: str, **arguments) -> dict:
    tools = ToolRegistry(
        {"catalog": CatalogService(repository), "payment": PaymentService(repository)}
    )
    return json.loads(tools.execute(tool, arguments).as_text())["value"]


def test_out_of_stock_product_is_reported_with_available_alternatives(repository) -> None:
    value = _tool_value(repository, "search_catalog", name="Giannini GF-3D")

    product = value["products"][0]
    assert product["availability"] == "out_of_stock"
    assert "temporariamente indisponível" in product["customer_guidance"]
    alternatives = [p["product_id"] for p in value["available_alternatives"]]
    assert alternatives == [4, 6, 5]  # same category, closest price first, only available
    assert all("availability" not in p for p in value["available_alternatives"])


def test_discontinued_product_is_never_offered_even_with_stock(repository) -> None:
    value = _tool_value(repository, "search_catalog", name="Ibanez Bass 2X")

    assert value["products"][0]["availability"] == "discontinued"
    assert "não faz mais parte do catálogo" in value["products"][0]["customer_guidance"]
    assert "available_alternatives" not in value  # no other available bass in the snapshot


def test_detail_of_discontinued_product_includes_equivalents(repository) -> None:
    value = _tool_value(repository, "product_detail", reference="2")

    assert value["product"]["availability"] == "discontinued"
    assert [p["product_id"] for p in value["available_alternatives"]] == [4, 6, 5]


def test_coming_soon_and_unknown_products_are_distinguished(repository) -> None:
    coming = _tool_value(repository, "search_catalog", name="Kala Barítono")
    missing = _tool_value(repository, "search_catalog", name="Fender Stratocaster")

    assert coming["products"][0]["availability"] == "coming_soon"
    assert missing["total"] == 0 and missing["products"] == []


def test_available_product_has_no_policy_noise(repository) -> None:
    value = _tool_value(repository, "search_catalog", name="Yamaha C40")

    assert "availability" not in value["products"][0]
    assert "available_alternatives" not in value
    assert "expired_promotions" not in value


def test_category_search_still_lists_only_available_products(repository) -> None:
    value = _tool_value(repository, "search_catalog", category="Violões")

    assert {p["product_id"] for p in value["products"]} == {4, 5, 6}


def test_expired_promotion_is_disclosed_and_never_applied(repository) -> None:
    search = _tool_value(repository, "search_catalog", name="Takamine GD20")
    quote = _tool_value(repository, "calculate_payment", product_id=5, overview=True)

    expired = search["expired_promotions"]["5"][0]
    assert expired["description"] == "Oferta Especial" and expired["status"] == "expired"
    assert "Nunca prometa esse desconto" in expired["customer_guidance"]
    assert quote["price_brl"] == "2199.00" and quote["promotion_active"] is False
    assert quote["expired_promotions"][0]["discount_percent"] == "12.00"


@pytest.mark.parametrize(
    ("local", "expected_open"),
    [
        (datetime(2026, 11, 4, 9, 0), True),     # Wednesday, opening minute
        (datetime(2026, 11, 4, 17, 59), True),
        (datetime(2026, 11, 4, 18, 0), False),   # closing time is exclusive
        (datetime(2026, 11, 7, 12, 30), True),   # Saturday morning
        (datetime(2026, 11, 7, 13, 0), False),
        (datetime(2026, 11, 8, 10, 0), False),   # Sunday
    ],
)
def test_business_hours_follow_the_manual(local: datetime, expected_open: bool) -> None:
    assert is_open(local.replace(tzinfo=STORE_TZ)) is expected_open


@pytest.mark.parametrize(
    ("local", "expected"),
    [
        (datetime(2026, 11, 4, 7, 30), "retorna hoje, às 09:00"),
        (datetime(2026, 11, 4, 20, 0), "retorna amanhã, às 09:00"),
        (datetime(2026, 11, 7, 14, 0), "retorna na segunda-feira, às 09:00"),
        (datetime(2026, 11, 6, 22, 0), "retorna amanhã, às 09:00"),  # Friday night -> Saturday
    ],
)
def test_out_of_hours_notice_states_when_the_team_returns(local: datetime, expected: str) -> None:
    notice = out_of_hours_notice(local.replace(tzinfo=STORE_TZ))

    assert notice is not None and expected in notice


def test_notice_is_none_during_business_hours_and_requires_timezone() -> None:
    assert out_of_hours_notice(datetime(2026, 11, 4, 12, 0, tzinfo=STORE_TZ)) is None
    with pytest.raises(ValueError):
        out_of_hours_notice(datetime(2026, 11, 4, 12, 0))


def test_conversation_appends_hours_notice_once_per_session(tmp_path: Path) -> None:
    sessions = SessionService(SQLiteSessionRepository.connect(tmp_path / "sessions.db"))
    llm = FakeLLM([FakeLLM.response("Olá! Como posso ajudar?"), FakeLLM.response("Claro!")])
    notice = "Obs.: no momento estamos fora do horário de atendimento da equipe da loja."
    app = ConversationService(sessions, llm, ToolRegistry(), hours_notice=lambda: notice)

    first = app.respond("Oi")
    second = app.respond("Obrigado", session_id=first.session_id)

    assert first.text.endswith(notice) and first.outcome == "success"
    assert second.text == "Claro!"


def test_conversation_without_notice_provider_is_unchanged(tmp_path: Path) -> None:
    sessions = SessionService(SQLiteSessionRepository.connect(tmp_path / "sessions.db"))
    app = ConversationService(sessions, FakeLLM([FakeLLM.response("Olá!")]), ToolRegistry())

    assert app.respond("Oi").text == "Olá!"
