"""Command-line delivery adapter for policy questions."""

from __future__ import annotations

import argparse
from pathlib import Path

from .catalog import CatalogError, PaymentResult, Product
from .catalog_service import CatalogService
from .catalog_sqlite import SQLiteCatalogRepository
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
        "--catalog-action", choices=("search", "detail", "payment"), help="Catalog action"
    )
    parser.add_argument("--name", help="Product name criterion")
    parser.add_argument("--category", help="Category criterion")
    parser.add_argument("--maximum-budget", help="Maximum BRL budget")
    parser.add_argument("--product", help="Product ID or exact name for detail")
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
                repository.ingest(args.products_csv, args.categories_csv, args.promotions_csv)
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
            "NÃ£o foi possÃ­vel consultar o catÃ¡logo com seguranÃ§a. "
            "Confirme o snapshot e tente novamente."
        )
        return 2
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
        f"EspecificaÃ§Ãµes: {specs}\n"
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


if __name__ == "__main__":
    raise SystemExit(main())
