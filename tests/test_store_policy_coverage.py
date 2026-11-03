import csv
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from emporio.catalog_sqlite import SQLiteCatalogRepository
from emporio.conversation import ConversationService
from emporio.correios import (
    CorreiosUnavailable,
    generate_fake_tracking_code,
    validate_tracking_code,
)
from emporio.llm import FakeLLM
from emporio.order import AuthorizedPrincipal
from emporio.order_service import OrderService
from emporio.payment_service import PaymentCalculationError, PaymentService
from emporio.post_sale import PostSaleService, SQLiteComplaintRepository
from emporio.session_service import SessionService
from emporio.session_sqlite import SQLiteSessionRepository
from emporio.shipping import Package, ShippingService
from emporio.simulators import MockWhatsAppChannel, mock_whatsapp_config
from emporio.tools import ToolRegistry
from emporio.whatsapp import WhatsAppWebhookAdapter

FIELDS = ["product_id", "price_brl", "name", "category_id", "description", "stock_quantity",
          "status", "specs", "created_at", "package_weight_kg", "package_length_cm",
          "package_width_cm", "package_height_cm"]
ORDER_FIELDS = ["order_id", "customer_id", "order_date", "status", "total_brl", "payment_method",
                "tracking_code", "estimated_delivery", "notes"]


def write(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def catalog(tmp_path, price="2500.00"):
    products = tmp_path / "products.csv"
    write(products, FIELDS, [{"product_id": "1", "price_brl": price, "name": "Piano",
        "category_id": "1", "description": "teste", "stock_quantity": "1", "status": "active",
        "specs": "{}", "created_at": "2026-01-01T00:00:00Z", "package_weight_kg": "8",
        "package_length_cm": "40", "package_width_cm": "30", "package_height_cm": "20"}])
    customers = tmp_path / "customers.csv"
    write(customers, ["customer_id", "name", "phone", "email", "city"], [{
        "customer_id": "1", "name": "Cliente", "phone": "1", "email": "x@y.invalid",
        "city": "Campo Grande",
    }])
    orders = tmp_path / "orders.csv"
    write(orders, ORDER_FIELDS, [{"order_id": "1", "customer_id": "1",
        "order_date": "2026-11-03T00:00:00Z",
        "status": "pending", "total_brl": price, "payment_method": "debit", "tracking_code": "",
        "estimated_delivery": "", "notes": ""}])
    items = tmp_path / "items.csv"
    write(items, ["order_id", "quantity", "product_id"], [{
        "order_id": "1", "quantity": "1", "product_id": "1",
    }])
    repo = SQLiteCatalogRepository.connect(tmp_path / "catalog.db")
    repo.ingest(products, customers_csv=customers, orders_csv=orders, order_items_csv=items,
                data_as_of=datetime(2026, 11, 3, tzinfo=timezone.utc))
    return repo


def test_debit_package_and_atomic_order_snapshot(tmp_path):
    repo = catalog(tmp_path)
    product = repo.find_by_id(1)
    assert product.package_weight_kg == Decimal("8.00")
    assert repo.find_owned_order(1, AuthorizedPrincipal(1)).payment_method == "debit"


def test_remote_shipping_is_complete_and_simulated():
    result = ShippingService().analyze(
        "São Paulo", order_total=Decimal("800"), cep="01001000",
        package=Package(Decimal("2"), Decimal("20"), Decimal("20"), Decimal("20")),
    )
    assert result.complete and not result.local
    assert {option.carrier for option in result.options} == {"Correios", "Jadlog"}
    assert all(option.simulated and option.tracking for option in result.options)


def test_remote_shipping_uses_stored_product_package_data(tmp_path):
    repo = catalog(tmp_path)
    result = ShippingService().analyze_product(
        repo.find_by_id(1), "Sao Paulo", order_total=Decimal("800"), cep="01001000"
    )
    assert result.complete and result.options[0].price_brl == Decimal("44.90")


def test_shipping_requires_data_and_quotes_oversized_package():
    incomplete = ShippingService().analyze("São Paulo", order_total=Decimal("800"), cep="01001000")
    assert not incomplete.complete and not incomplete.options
    large = ShippingService().analyze("São Paulo", order_total=Decimal("800"), cep="01001000",
        package=Package(Decimal("31"), Decimal("20"), Decimal("20"), Decimal("20")))
    assert large.options[0].price_brl is None


def test_payment_split_does_not_apply_to_ineligible_or_promotional_total(tmp_path):
    repo = catalog(tmp_path)
    options = PaymentService(repo).calculate_combinations(1)
    assert options[0].pix_amount_brl == Decimal("500.00")
    with pytest.raises(PaymentCalculationError):
        PaymentService.calculate_combinations_for_total(Decimal("2000.00"))


def test_tracking_codes_are_valid_and_deterministic():
    code = generate_fake_tracking_code("order-1")
    assert code == generate_fake_tracking_code("order-1")
    assert validate_tracking_code(code) == code
    with pytest.raises(CorreiosUnavailable):
        validate_tracking_code("AB123")


def test_mock_whatsapp_uses_conversation_service_and_fake_llm(tmp_path):
    conversation = ConversationService(
        SessionService(SQLiteSessionRepository.connect(tmp_path / "sessions.db")),
        FakeLLM([FakeLLM.response("Olá, resposta simulada.")]),
        ToolRegistry(),
    )
    channel = MockWhatsAppChannel(WhatsAppWebhookAdapter(mock_whatsapp_config()))
    first = channel.deliver(conversation, message_id="coverage-1", text="olÃ¡")
    second = channel.deliver(conversation, message_id="coverage-1", text="olÃ¡")
    assert first.response.text == "Olá, resposta simulada."
    assert second.duplicate


def test_post_sale_is_authorized_and_persisted(tmp_path):
    repo = catalog(tmp_path)
    service = PostSaleService(OrderService(repo), SQLiteComplaintRepository(repo._connection))
    principal = AuthorizedPrincipal(1)
    complaint = service.create_complaint(1, principal, category="troca", description="Produto")
    assert complaint and service.request_return(1, principal).return_code.startswith("DEV-1-")
    assert service.create_complaint(
        1, AuthorizedPrincipal(2), category="x", description="y"
    ) is None
