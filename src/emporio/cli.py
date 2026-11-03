"""Command-line delivery adapter for policy questions."""

from __future__ import annotations

import argparse
from pathlib import Path

from .policy import PolicyError
from .policy_source import PdfPolicyRetriever
from .service import PolicyService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Empório da Música policy assistant")
    parser.add_argument("--policy-source", type=Path, required=True, help="Path to the policy PDF")
    parser.add_argument("--query", required=True, help="Question in Brazilian Portuguese")
    parser.add_argument("--document-version", default="local", help="Policy document version")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        retriever = PdfPolicyRetriever.from_path(
            args.policy_source,
            document_version=args.document_version,
        )
        print(PolicyService(retriever).answer(args.query).render())
        return 0
    except PolicyError:
        print(
            "Não foi possível consultar o manual da loja com segurança. "
            "Confirme a fonte e tente novamente."
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
