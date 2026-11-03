"""Command-line delivery adapter for policy questions."""

from __future__ import annotations

import argparse
from pathlib import Path

from .catalog import CatalogError, Product
from .catalog_service import CatalogService
from .catalog_sqlite import SQLiteCatalogRepository
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
    parser.add_argument("--catalog-action", choices=("search", "detail"), help="Catalog action")
    parser.add_argument("--name", help="Product name criterion")
    parser.add_argument("--category", help="Category criterion")
    parser.add_argument("--maximum-budget", help="Maximum BRL budget")
    parser.add_argument("--product", help="Product ID or exact name for detail")
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
                repository.ingest(args.products_csv, args.categories_csv)
            service = CatalogService(repository)
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


if __name__ == "__main__":
    raise SystemExit(main())
