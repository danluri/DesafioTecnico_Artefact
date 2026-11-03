"""Command-line delivery adapter for policy questions."""

from __future__ import annotations

import argparse
from pathlib import Path

from .catalog import CatalogError, PaymentResult, Product
from .catalog_service import CatalogService
from .catalog_sqlite import SQLiteCatalogRepository
from .order import AuthorizedPrincipal, OrderStatusSnapshot
from .order_service import OrderService
from .payment_service import PaymentService
from .policy import PolicyError
from .policy_source import PdfPolicyRetriever
from .service import PolicyService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Empório da Música policy assistant")
    parser.add_argument("--policy-source", type=Path, help="Path to the policy PDF")
    parser.add_argument("--query", help="Question in Brazilian Portuguese")
    parser.add_argument("--document-version", default="local", help="Policy document version")
    parser.add_argument("--catalog-db", type=Path, help="SQLite operational snapshot database")
    parser.add_argument("--products-csv", type=Path, help="Products CSV to ingest atomically")
    parser.add_argument("--categories-csv", type=Path, help="Categories CSV to ingest atomically")
    parser.add_argument("--promotions-csv", type=Path, help="Promotions CSV to ingest atomically")
    parser.add_argument(
        "--catalog-action", choices=("search", "detail", "payment", "order-status"),
        help="Catalog or order snapshot action"
    )
    parser.add_argument("--name", help="Product name criterion")
    parser.add_argument("--category", help="Category criterion")
    parser.add_argument("--maximum-budget", help="Maximum BRL budget")
    parser.add_argument("--product", help="Product ID or exact name for detail")
    parser.add_argument("--order", "--order-id", dest="order_reference", help="Order reference")
    parser.add_argument(
        "--demo-server-principal", type=int,
        help="Demo only: customer ID supplied as an explicit server-established principal",
    )
    parser.add_argument(
        "--customers-csv", type=Path, help="Customers CSV for order snapshot ingestion"
    )
    parser.add_argument("--orders-csv", type=Path, help="Orders CSV for order snapshot ingestion")
    parser.add_argument(
        "--order-items-csv", type=Path, help="Order items CSV for order snapshot ingestion"
    )
    parser.add_argument("--pix", action="store_true", help="Calculate the PIX option")
    parser.add_argument("--installments", type=int, help="Number of installments (1 to 12)")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--offset", type=int, default=0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.catalog_action:
            if not args.catalog_db:
                raise CatalogError("--catalog-db is required for catalog actions")
            repository = SQLiteCatalogRepository.connect(args.catalog_db)
            if args.products_csv:
                repository.ingest(
                    args.products_csv, args.categories_csv, args.promotions_csv,
                    customers_csv=args.customers_csv, orders_csv=args.orders_csv,
                    order_items_csv=args.order_items_csv,
                )
            elif any((args.customers_csv, args.orders_csv, args.order_items_csv)):
                raise CatalogError("products source is required for a complete snapshot")
            if args.catalog_action == "order-status":
                principal = (
                    AuthorizedPrincipal(args.demo_server_principal)
                    if args.demo_server_principal is not None else None
                )
                result = OrderService(repository).get_status(args.order_reference, principal)
                print(_render_order(result) if result else OrderService.safe_message())
                return 0
            service = CatalogService(repository)
            if args.catalog_action == "payment":
                if not args.product or not args.product.isdigit():
                    raise CatalogError("--product must be a product ID for payment actions")
                result = PaymentService(repository).calculate(
                    int(args.product), pix=args.pix, installments=args.installments
                )
                print(_render_payment(result))
                return 0
            if args.catalog_action == "detail":
                result = service.detail(args.product or "")
                if not result:
                    print("Não encontrei um produto válido com esse identificador no snapshot.")
                elif isinstance(result, tuple):
                    print("Encontrei mais de um produto. Informe o ID ou um nome mais específico:")
                    for product in result:
                        print(f"- {product.name} (ID {product.product_id})")
                else:
                    print(_render_product(result.product))
                return 0
            result = service.search(
                name=args.name,
                category=args.category,
                maximum_budget=args.maximum_budget,
                limit=args.limit,
                offset=args.offset,
            )
            if not result.products:
                print(
                    "Não encontrei produtos disponíveis que atendam a esses critérios no snapshot."
                )
            else:
                print(
                    "Snapshot de disponibilidade de "
                    f"{result.snapshot.data_as_of.isoformat()} (não é estoque em tempo real):"
                )
                for product in result.products:
                    print(
                        f"- {product.name} (ID {product.product_id}): "
                        f"{_brl(product.price_brl)}; {product.stock_quantity} em estoque"
                    )
                print(
                    f"Página: {args.offset // args.limit + 1}; total de resultados: {result.total}"
                )
            return 0
        if not args.policy_source or not args.query:
            raise PolicyError("policy source and query are required")
        retriever = PdfPolicyRetriever.from_path(
            args.policy_source,
            document_version=args.document_version,
        )
        print(PolicyService(retriever).answer(args.query).render())
        return 0
    except CatalogError:
        print(
            "cat\u00e1logo: n\u00e3o foi poss\u00edvel consultar o cat\u00e1logo "
            "com seguran\u00e7a. "
            "Confirme o snapshot e tente novamente."
        )
        return 2
    except (ValueError, TypeError):
        print(OrderService.safe_message())
        return 0
    except PolicyError:
        print(
            "Não foi possível consultar o manual da loja com segurança. "
            "Confirme a fonte e tente novamente."
        )
        return 2


def _brl(value: object) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _render_product(product: Product) -> str:
    specs = ", ".join(f"{key}: {value}" for key, value in product.specs.items())
    return (
        f"Especificacoes: {specs}\n"
        f"{product.name} (ID {product.product_id})\nDescrição: {product.description}\n"
        f"Preço no snapshot: {_brl(product.price_brl)}\n"
        f"Disponibilidade: {product.stock_quantity} unidades; status {product.status}\n"
        f"Dados de: {product.snapshot.data_as_of.isoformat()} (não é informação em tempo real)."
    )


def _render_payment(payment: PaymentResult) -> str:
    lines = [
        f"{payment.product.name} (ID {payment.product.product_id})",
        f"Preço original: {_brl(payment.original_price_brl)}",
        f"Desconto de promoção: {_brl(payment.discount_brl)}"
        + (f" ({payment.discount_percent}%)" if payment.discount_percent is not None else ""),
        f"Preço efetivo: {_brl(payment.effective_price_brl)}",
    ]
    if payment.promotion:
        lines.append(
            f"Promoção ativa no snapshot: {payment.promotion.description} "
            f"(ID {payment.promotion.promotion_id})"
        )
    if payment.pix_requested:
        pix_value = (
            payment.pix_price_brl
            if payment.pix_price_brl is not None
            else payment.effective_price_brl
        )
        lines.append(
            f"PIX: {_brl(pix_value)}"
            + (" (5% aplicado)" if payment.pix_applied else " (sem acúmulo com promoção)")
        )
    if payment.installments:
        lines.append(
            f"Parcelamento: {payment.installments.count}x de "
            f"{_brl(payment.installments.amount_brl)}"
        )
        if payment.installments.final_amount_brl != payment.installments.amount_brl:
            lines.append(f"Última parcela ajustada: {_brl(payment.installments.final_amount_brl)}")
    lines.append(f"Frete: {_brl(payment.shipping_brl)}")
    lines.append(
        f"Snapshot: {payment.snapshot.data_as_of.isoformat()} "
        "(não é preço em tempo real)."
    )
    lines.append("; ".join(payment.assumptions))
    return "\n".join(lines)


def _render_order(order: OrderStatusSnapshot) -> str:
    lines = [
        f"Pedido {order.order_id}: {order.status}",
        f"Data do pedido: {order.order_date.isoformat()}",
        f"Total: {_brl(order.total_brl)}",
        f"Pagamento: {order.payment_method}",
        f"Itens: {', '.join(f'{item.product_id} ({item.quantity} un.)' for item in order.items)}",
        f"Snapshot de {order.snapshot.data_as_of.isoformat()} (não é rastreamento em tempo real).",
        order.tracking_message,
    ]
    if order.estimated_delivery:
        lines.insert(5, f"Previsão no snapshot: {order.estimated_delivery}")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
